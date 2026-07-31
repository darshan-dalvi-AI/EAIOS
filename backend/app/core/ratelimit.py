"""Rate limiting — token bucket per client, applied as ASGI middleware.

Default backend is in-process (thread-safe, zero deps). When REDIS_URL is
configured and the redis client is importable, buckets live in Redis so
limits hold across replicas (K8s HPA) — same interface, swapped silently.

Rules are conservative-but-generous: they stop brute force and runaway
loops without ever throttling an honest demo.
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

log = logging.getLogger("eaios.ratelimit")


@dataclass(frozen=True)
class Rule:
    name: str
    capacity: int          # tokens per window
    per_seconds: int       # window length
    by_user: bool = True   # key on bearer token when present (else IP)
    # Authentication routes additionally key on the *account* being targeted,
    # so a distributed attack on one account is limited even when every
    # request arrives from a different address.
    by_account: bool = False
    # Repeated abuse of an auth route backs off exponentially instead of
    # locking the account, which would itself be a denial-of-service vector.
    backoff: bool = False


def _r(name: str, cap_default: int, per_default: int, **kw) -> Rule:
    """Build a rule, letting deployment override both numbers.

    Thresholds are read from settings so they can be tuned per environment
    (a public demo wants different numbers from an internal deployment)
    without editing code. Env names follow RL_<NAME>_CAPACITY / _WINDOW.
    """
    raw_cap = int(getattr(settings, f"RL_{name.upper().replace('-', '_')}_CAPACITY", 0))
    raw_per = int(getattr(settings, f"RL_{name.upper().replace('-', '_')}_WINDOW", 0))
    # Sentinels, so "turn this limit off" and "leave it at the default" are
    # different instructions and neither is a silent surprise:
    #   -1  → explicitly UNLIMITED (the guard skips the rule)
    #    0  → unset, use the code default below
    #   >0  → that exact value
    if raw_cap < 0:
        return Rule(name, -1, per_default, **kw)
    cap = raw_cap or cap_default
    per = raw_per or per_default
    return Rule(name, int(cap), int(per), **kw)


def build_rules() -> list[tuple[str, str, Rule]]:
    """Method, path-prefix → rule. Tiered by how sensitive the endpoint is:
    strict on authentication, moderate on public/expensive routes, generous
    on ordinary authenticated actions."""
    return [
        # ── tier 1: authentication — strictest, per-IP AND per-account ──
        ("POST", "/api/auth/login",    _r("login",    10, 60, by_user=False, by_account=True, backoff=True)),
        ("POST", "/api/auth/signup",   _r("signup",    5, 3600, by_user=False, backoff=True)),
        ("POST", "/api/auth/register", _r("register",  5, 3600, by_user=False, backoff=True)),
        # Each call creates a whole tenant with no password in front of it, so
        # this is the cheapest thing on the site to abuse. Generous enough for a
        # classroom demoing it at once, tight enough that a script cannot fill
        # the database with throwaway workspaces.
        ("POST", "/api/auth/demo",     _r("demo",     10, 3600, by_user=False, backoff=True)),
        # ── tier 2: expensive or externally-reaching authenticated work ──
        ("POST", "/api/documents",     _r("upload",   40, 3600)),
        ("POST", "/api/connectors",    _r("connector", 20, 3600)),
        ("POST", "/api/agents/sql",    _r("sql",      60, 60)),
        ("POST", "/api/workflows",     _r("wf-run",   30, 60)),
        ("POST", "/api/reports",       _r("report",   30, 60)),
        # ── tier 3: ordinary authenticated interaction — generous ──
        ("POST", "/api/chat",          _r("chat",     60, 60)),
        ("GET",  "/api/search",        _r("search",  120, 60)),
        # ── destructive administration ──
        ("DELETE", "/api/orgs",        _r("org-del",   5, 3600)),
    ]


RULES: list[tuple[str, str, Rule]] = build_rules()


def reload_rules() -> None:
    """Re-read thresholds from settings (used by tests and after config change)."""
    global RULES
    RULES = build_rules()


class _MemoryBuckets:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # key → (tokens, last_refill)
        self._lock = threading.Lock()

    def allow(self, key: str, rule: Rule) -> tuple[bool, int]:
        now = time.monotonic()
        rate = rule.capacity / rule.per_seconds
        with self._lock:
            tokens, last = self._buckets.get(key, (float(rule.capacity), now))
            tokens = min(rule.capacity, tokens + (now - last) * rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return True, 0
            self._buckets[key] = (tokens, now)
            return False, max(1, int((1.0 - tokens) / rate))


class _RedisBuckets:  # pragma: no cover — exercised only with a live Redis
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url, socket_timeout=0.5)

    def allow(self, key: str, rule: Rule) -> tuple[bool, int]:
        # fixed window (INCR + EXPIRE): simpler than a Lua bucket, close enough
        window = int(time.time()) // rule.per_seconds
        rkey = f"rl:{key}:{window}"
        try:
            count = self._r.incr(rkey)
            if count == 1:
                self._r.expire(rkey, rule.per_seconds)
            if count <= rule.capacity:
                return True, 0
            ttl = self._r.ttl(rkey)
            return False, max(1, ttl if ttl and ttl > 0 else rule.per_seconds)
        except Exception:  # noqa: BLE001 — Redis down must never break requests
            return True, 0


def _make_backend():
    if settings.REDIS_URL:
        try:
            backend = _RedisBuckets(settings.REDIS_URL)
            log.info("rate limiting backed by Redis")
            return backend
        except Exception:  # noqa: BLE001
            log.warning("REDIS_URL set but unusable — falling back to in-memory buckets")
    return _MemoryBuckets()


_backend = None


def get_backend():
    global _backend
    if _backend is None:
        _backend = _MemoryBuckets() if not settings.REDIS_URL else _make_backend()
    return _backend


def _client_ip(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return ip


def _client_key(request: Request, rule: Rule) -> str:
    if rule.by_user:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            digest = hashlib.sha256(auth.encode()).hexdigest()[:16]
            return f"{rule.name}:u:{digest}"
    return f"{rule.name}:ip:{_client_ip(request)}"


# ── exponential backoff for authentication routes ────────────────────────
# A hard lockout is itself an attack: anyone who knows an email can lock the
# owner out. Instead each additional rejection doubles the wait for that
# key, capped, and the penalty decays once the caller behaves.
_penalties: dict[str, tuple[int, float]] = {}   # key → (strikes, expires_at)
_pen_lock = threading.Lock()
_BACKOFF_BASE = 2          # seconds
_BACKOFF_MAX = 15 * 60     # never wait longer than 15 minutes


def _backoff_check(key: str) -> int:
    """Return seconds still to wait, or 0 if the caller may proceed."""
    now = time.monotonic()
    with _pen_lock:
        strikes, expires = _penalties.get(key, (0, 0.0))
        if strikes and now >= expires and now - expires > _BACKOFF_MAX:
            _penalties.pop(key, None)          # long-quiet caller forgiven
            return 0
        return max(0, int(expires - now))


def _backoff_strike(key: str) -> int:
    """Record a rejection and return the new wait in seconds."""
    now = time.monotonic()
    with _pen_lock:
        strikes, _ = _penalties.get(key, (0, 0.0))
        strikes += 1
        wait = min(_BACKOFF_BASE * (2 ** (strikes - 1)), _BACKOFF_MAX)
        _penalties[key] = (strikes, now + wait)
        return wait


def clear_backoff(key_prefix: str = "") -> None:
    """Forget penalties — called on a *successful* login, and by tests."""
    with _pen_lock:
        for k in [k for k in _penalties if not key_prefix or k.startswith(key_prefix)]:
            _penalties.pop(k, None)


def _match(method: str, path: str) -> Rule | None:
    for m, prefix, rule in RULES:
        if method == m and path.startswith(prefix):
            return rule
    return None


def _too_many(rule: Rule, retry_after: int) -> JSONResponse:
    """One shape of refusal for every limiter, with no internal detail."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests. Please try again in {retry_after}s."},
        headers={"Retry-After": str(max(1, retry_after))},
    )


async def _target_account(request: Request) -> str | None:
    """Read the email an auth request is aimed at, without consuming the body.

    Starlette caches the body on the request, so the route handler still
    receives it after we peek."""
    try:
        body = await request.body()
        if not body or len(body) > 8192:
            return None
        import json
        data = json.loads(body)
        email = data.get("email")
        return email.strip().lower()[:255] if isinstance(email, str) else None
    except Exception:  # noqa: BLE001 — malformed body is the route's problem, not ours
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)
        rule = _match(request.method, request.url.path)
        if rule is None or rule.capacity < 0:   # no rule, or explicitly unlimited
            return await call_next(request)

        backend = get_backend()
        keys = [_client_key(request, rule)]

        # Authentication routes are additionally limited per targeted account,
        # so rotating source addresses does not buy extra attempts.
        if rule.by_account:
            account = await _target_account(request)
            if account:
                digest = hashlib.sha256(account.encode()).hexdigest()[:16]
                keys.append(f"{rule.name}:acct:{digest}")

        # Serving a penalty from earlier abuse?
        if rule.backoff:
            for k in keys:
                wait = _backoff_check(k)
                if wait:
                    log.warning("429 (backoff %ss) %s %s", wait, request.method, request.url.path)
                    return _too_many(rule, wait)

        for k in keys:
            allowed, retry_after = backend.allow(k, rule)
            if not allowed:
                if rule.backoff:
                    retry_after = max(retry_after, _backoff_strike(k))
                log.warning("429 %s %s (%s)", request.method, request.url.path, rule.name)
                return _too_many(rule, retry_after)

        response = await call_next(request)

        # A successful sign-in clears the penalty for that account and address.
        if rule.backoff and response.status_code < 400:
            for k in keys:
                clear_backoff(k)
        return response
