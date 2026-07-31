"""Auth primitives: PBKDF2 password hashing + HS256 JWTs.
Implemented on the stdlib (hashlib/hmac) — no external crypto dependencies,
constant-time comparisons throughout."""
import base64
import hashlib
import hmac
import json
import os
import time

from app.core.config import settings

# OWASP's current guidance for PBKDF2-HMAC-SHA256, read from settings so a
# deployment (or the test suite) can choose its own cost. Raising it is safe:
# the cost is stored inside each hash, and accounts are re-hashed on their
# next successful sign-in (see needs_rehash).
PBKDF2_ITERATIONS = settings.PASSWORD_HASH_ITERATIONS
LEGACY_ITERATIONS = 100_000   # hashes written before the format carried a cost


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── Passwords ────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash with the current cost, recording it so the cost can be raised later.

    Format: ``pbkdf2_sha256$<iterations>$<salt>$<digest>``. The legacy format
    (``<salt>$<digest>``, fixed at 100 000 rounds) is still verified, so
    raising the cost never locks anyone out of an existing account."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _parse_hash(hashed: str) -> tuple[int, str, str] | None:
    parts = hashed.split("$")
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        try:
            return int(parts[1]), parts[2], parts[3]
        except ValueError:
            return None
    if len(parts) == 2:                       # legacy: fixed iteration count
        return LEGACY_ITERATIONS, parts[0], parts[1]
    return None


def verify_password(password: str, hashed: str) -> bool:
    parsed = _parse_hash(hashed)
    if parsed is None:
        return False
    iterations, salt_hex, digest_hex = parsed
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(expected.hex(), digest_hex)


def needs_rehash(hashed: str) -> bool:
    """True when a stored hash uses an older, cheaper cost than we now require.

    Called after a *successful* sign-in — the only moment the plaintext is
    available — so accounts upgrade silently as people log in."""
    parsed = _parse_hash(hashed)
    return parsed is None or parsed[0] < PBKDF2_ITERATIONS


# ── JWT (HS256) ──────────────────────────────────────────────────

def create_token(sub: str, role: str, minutes: int | None = None) -> str:
    # Sub-second issued-at: token revocation (see User.token_epoch) compares
    # this against the logout time, and integer seconds would leave a one-second
    # window where a just-issued token and a just-logged-out epoch look equal.
    now = time.time()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": int(now) + 60 * (minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}"
    signature = hmac.new(settings.SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


def decode_token(token: str) -> dict | None:
    """Return the payload if signature and expiry are valid, else None."""
    try:
        head, body, sig = token.split(".")
        expected = hmac.new(settings.SECRET_KEY.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64(expected), sig):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
