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

PBKDF2_ITERATIONS = 100_000


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── Passwords ────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        salt_hex, digest_hex = hashed.split("$")
    except ValueError:
        return False
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


# ── JWT (HS256) ──────────────────────────────────────────────────

def create_token(sub: str, role: str, minutes: int | None = None) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + 60 * (minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES),
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
