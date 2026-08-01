"""HTTP security headers.

These are the cheapest defences available: a few response headers that shut
down entire attack classes — clickjacking, MIME sniffing, protocol downgrade,
referrer leakage — without touching application logic.

The Content-Security-Policy is written for how K-OS actually loads: a
same-origin single-page app, one optional third-party script (Google Identity
Services, only when the connector is configured), a WebSocket for presence,
and blob/data URLs for camera preview and generated exports. It is enforced,
not report-only, so a policy that breaks the app breaks the tests too.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings

# Google Identity Services is only reachable when the connector is set up.
_GIS = "https://accounts.google.com https://apis.google.com"
# The interface loads its three typefaces from Google Fonts. Verified in a
# real browser: omitting these silently strips the app's typography, which a
# server-side test cannot see.
_FONTS_CSS = "https://fonts.googleapis.com"
_FONTS_FILES = "https://fonts.gstatic.com"

CSP = "; ".join([
    "default-src 'self'",
    # 'unsafe-inline' is required for the small inline bootstrap and for
    # React's style attributes; no 'unsafe-eval', so injected code cannot be
    # turned into executable script.
    f"script-src 'self' 'unsafe-inline' {_GIS}",
    f"style-src 'self' 'unsafe-inline' {_FONTS_CSS}",
    "img-src 'self' data: blob:",
    f"font-src 'self' data: {_FONTS_FILES}",
    "media-src 'self' blob:",                      # camera preview, recorded audio
    f"connect-src 'self' ws: wss: {_GIS} {_FONTS_CSS} {_FONTS_FILES}",   # API + presence socket
    f"frame-src 'self' {_GIS}",                    # Google consent popup
    "object-src 'none'",                           # no Flash/embed plugins
    "base-uri 'self'",                             # cannot repoint relative URLs
    "form-action 'self'",                          # cannot post credentials elsewhere
    "frame-ancestors 'none'",                      # modern clickjacking defence
])

BASE_HEADERS = {
    "X-Frame-Options": "DENY",                     # clickjacking (legacy browsers)
    "X-Content-Type-Options": "nosniff",           # no MIME sniffing
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",   # isolates the browsing context
    "Permissions-Policy": (                        # deny hardware we do not use
        "geolocation=(), payment=(), usb=(), magnetometer=(), accelerometer=(), "
        "camera=(self), microphone=(self)"         # video calls need these on self
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in BASE_HEADERS.items():
            response.headers.setdefault(key, value)

        # A policy this strict would block the interactive API docs, which
        # only exist outside production anyway.
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            response.headers.setdefault("Content-Security-Policy", CSP)

        # Only meaningful over TLS, and only safe to send in production —
        # sending it from localhost would pin the browser to https there too.
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        # Advertising the server and framework only helps someone choosing an
        # exploit to try. (Starlette's MutableHeaders supports __delitem__ but
        # not pop, and deleting an absent key raises.)
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]
        response.headers["Server"] = "K-OS"
        return response
