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


# method, path-prefix → rule
RULES: list[tuple[str, str, Rule]] = [
    ("POST", "/api/auth/login",     Rule("login",    20, 60, by_user=False)),
    ("POST", "/api/auth/register",  Rule("register", 10, 60, by_user=False)),
    ("POST", "/api/chat",           Rule("chat",     60, 60)),
    ("POST", "/api/documents",      Rule("upload",   60, 3600)),
    ("POST", "/api/workflows",      Rule("wf-run",   30, 60)),
    ("POST", "/api/agents/sql",     Rule("sql",      60, 60)),
]


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


def _client_key(request: Request, rule: Rule) -> str:
    if rule.by_user:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            digest = hashlib.sha256(auth.encode()).hexdigest()[:16]
            return f"{rule.name}:u:{digest}"
    ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return f"{rule.name}:ip:{ip}"


def _match(method: str, path: str) -> Rule | None:
    for m, prefix, rule in RULES:
        if method == m and path.startswith(prefix):
            return rule
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)
        rule = _match(request.method, request.url.path)
        if rule is None:
            return await call_next(request)
        allowed, retry_after = get_backend().allow(_client_key(request, rule), rule)
        if allowed:
            return await call_next(request)
        log.warning("429 %s %s (%s)", request.method, request.url.path, rule.name)
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded ({rule.capacity}/{rule.per_seconds}s). "
                               f"Try again in {retry_after}s."},
            headers={"Retry-After": str(retry_after)},
        )
