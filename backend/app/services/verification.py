"""Proving that someone owns the email address they signed up with.

Before this, anyone could type any address and receive a workspace — so a
signup told us nothing about who the person was, and there was no reliable way
to reach them for a password reset or a renewal notice.

Two routes, both ending in the same guarantee:

* **Google** — Google asserts the address, so nothing is sent and nothing
  expires. Works for gmail.com *and* company Google Workspace domains, which
  is what a paying business actually uses.
* **Emailed code** — a six-digit code for everyone else. Stored hashed with an
  expiry and an attempt limit, because a code sitting in plaintext in the
  database is a second copy of the credential.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import User

log = logging.getLogger("eaios.verify")

CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 6

# Throwaway inbox providers. Someone using one cannot be contacted later, so a
# workspace registered against one is a support liability rather than a lead.
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "throwawaymail.com", "yopmail.com", "trashmail.com",
    "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc",
    "fakeinbox.com", "mintemail.com", "spamgourmet.com", "mailnesia.com",
}


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()


def is_disposable(email: str) -> bool:
    return domain_of(email) in DISPOSABLE_DOMAINS


def _hash(code: str, email: str) -> str:
    """Bind the code to the address so a code cannot be replayed elsewhere."""
    return hashlib.pbkdf2_hmac(
        "sha256", code.encode(), (settings.SECRET_KEY + email.lower()).encode(), 20_000
    ).hex()


def issue(db: Session, user: User) -> str:
    """Generate a fresh code, store only its hash, and return the plaintext
    once so the caller can send it."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.verify_code_hash = _hash(code, user.email)
    user.verify_expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
    user.verify_attempts = 0
    db.commit()
    return code


def check(db: Session, user: User, code: str) -> tuple[bool, str]:
    """Return (ok, reason). Reasons are safe to show the person."""
    if user.email_verified:
        return True, "already verified"
    if not user.verify_code_hash or not user.verify_expires_at:
        return False, "No code has been requested. Send a new one."

    expires = user.verify_expires_at
    if expires.tzinfo is None:                     # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        return False, "That code has expired. Send a new one."

    if user.verify_attempts >= MAX_ATTEMPTS:
        return False, "Too many incorrect attempts. Send a new code."

    if not hmac.compare_digest(_hash(code.strip(), user.email), user.verify_code_hash):
        user.verify_attempts += 1
        db.commit()
        left = MAX_ATTEMPTS - user.verify_attempts
        return False, (f"That code isn't right. {left} attempt{'s' if left != 1 else ''} left."
                       if left > 0 else "Too many incorrect attempts. Send a new code.")

    user.email_verified = True
    user.verify_code_hash = None
    user.verify_expires_at = None
    user.verify_attempts = 0
    db.commit()
    log.info("email verified for %s", user.email)
    return True, "verified"
