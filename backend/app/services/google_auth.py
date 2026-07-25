"""Verifying a Google sign-in.

The browser hands us an ID token. That token is only meaningful if we check it
server-side — a client can send any string it likes, so trusting the decoded
payload without verification would be the same as trusting the caller.

We ask Google to validate the signature, then check three things ourselves:

* ``aud`` is *our* client id — a token minted for a different application must
  not be accepted here, otherwise anyone with any Google app could sign in.
* ``iss`` is Google.
* ``email_verified`` is true — Google itself distinguishes a confirmed address
  from one merely typed into a profile.

This works for gmail.com and for company Google Workspace domains, which is
what a paying business actually signs up with.
"""
import logging

from app.core.config import settings

log = logging.getLogger("eaios.google")

TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    """Raised with a message that is safe to show the person."""


def verify_id_token(id_token: str) -> dict:
    """Return {email, name, sub, hd} for a valid token, or raise."""
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Google sign-in isn't configured on this deployment.")
    if not id_token or len(id_token) > 4096:
        raise GoogleAuthError("That Google sign-in couldn't be read.")

    import httpx

    try:
        r = httpx.get(TOKENINFO, params={"id_token": id_token}, timeout=10, trust_env=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("google tokeninfo unreachable: %s", exc)
        raise GoogleAuthError("Couldn't reach Google to confirm your sign-in. Try again.") from exc

    if r.status_code != 200:
        raise GoogleAuthError("That Google sign-in has expired. Try again.")

    claims = r.json()

    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        # Someone presenting a token issued to another application.
        log.warning("google token audience mismatch: %s", str(claims.get("aud"))[:60])
        raise GoogleAuthError("That Google sign-in wasn't issued for this app.")

    if claims.get("iss") not in VALID_ISSUERS:
        raise GoogleAuthError("That sign-in didn't come from Google.")

    if str(claims.get("email_verified", "")).lower() not in ("true", "1"):
        raise GoogleAuthError("Google hasn't verified that email address.")

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise GoogleAuthError("That Google account has no email address.")

    return {
        "email": email,
        "name": (claims.get("name") or email.split("@")[0]).strip()[:120],
        "sub": claims.get("sub", ""),
        "hd": claims.get("hd", ""),          # Workspace domain, if a company account
    }
