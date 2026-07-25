"""Turning exceptions into messages that are safe to show a user.

Raw exception text is written for developers: it can contain connection
strings, file paths, SQL fragments, or — worst of all — the request URL an
HTTP client failed on, which for an OAuth sync includes the access token.

`public_message` returns something a user can act on, logs the full detail
with a short reference, and never echoes the original text.
"""
import logging
import re
import uuid

log = logging.getLogger("eaios.errors")

# Anything resembling a credential is scrubbed before the detail reaches a log
# aggregator, which is often less protected than the application itself.
_REDACT = [
    (re.compile(r"(access_token|token|api[_-]?key|password|secret)=[^&\s\"']+", re.I), r"\1=<redacted>"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{8,}|gsk_[A-Za-z0-9]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_.-]+)"), "<redacted>"),
    (re.compile(r"(postgres(?:ql)?://[^:]+:)[^@]+@", re.I), r"\1<redacted>@"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACT:
        text = pattern.sub(repl, text)
    return text


# Exception class name → message a user can actually do something about.
_FRIENDLY = {
    "ConnectError": "Could not reach the external service. Check the network or try again.",
    "ConnectTimeout": "The external service took too long to respond.",
    "ReadTimeout": "The external service took too long to respond.",
    "TimeoutException": "The operation timed out.",
    "HTTPStatusError": "The external service rejected the request. The credential may be expired.",
    "PermissionError": "The server could not access a required file.",
    "FileNotFoundError": "A required file is missing on the server.",
    "IntegrityError": "That change conflicts with existing data.",
    "OperationalError": "The database is temporarily unavailable.",
    "JSONDecodeError": "The external service returned a response we could not read.",
}


def public_message(exc: Exception, context: str = "") -> tuple[str, str]:
    """Return (user-safe message, reference id) and log the real cause.

    A ``ValueError`` raised by our own code is a message we *wrote for the
    user* ("paste an access token"), so it is passed through — redacted, and
    only when it is short enough to be a sentence rather than a dump. Every
    other exception is replaced, because its text was written for developers.
    """
    ref = uuid.uuid4().hex[:12]
    log.warning("%s failed ref=%s: %s", context or "operation", ref,
                redact(f"{type(exc).__name__}: {exc}")[:800], exc_info=True)

    if isinstance(exc, ValueError):
        intended = redact(str(exc)).strip()
        if 0 < len(intended) <= 240 and "\n" not in intended:
            return intended, ref

    friendly = _FRIENDLY.get(type(exc).__name__, "Something went wrong while completing this action.")
    return f"{friendly} (reference {ref})", ref
