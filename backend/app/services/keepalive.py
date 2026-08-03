"""Keeping a free-tier host awake by talking to ourselves.

Render's free plan suspends a service after ~15 minutes with no *inbound*
traffic, and waking it takes 30-50 seconds. A visitor who clicks a link and
waits a minute concludes the thing is broken, which is an expensive way to be
free.

So the app requests its own public URL on a timer. The request leaves the
container, goes out to the internet, and comes back through the platform's
router as ordinary inbound traffic — which is what the idle timer actually
measures. Once the service is up it keeps itself up.

Two things this deliberately is not:

* **Not a health check.** Nothing depends on the result. If the ping fails the
  app carries on; the only cost is that the host may fall asleep, which is
  where it started.
* **Not a wake-up call.** It can only keep a running service running. If the
  service does go down, nothing here brings it back — an *external* pinger is
  the belt to this pair of braces, and the two are complementary rather than
  alternatives.

Off unless ``KEEPALIVE_URL`` is set, so local development and self-hosted
installs never make surprise outbound requests.
"""
import logging

from app.core.config import settings

log = logging.getLogger("eaios.keepalive")

# Hosts that mean "this same container". Pinging one of these does travel a
# network stack, so it *looks* like it works — but it never leaves the machine,
# never reaches the platform's router, and so does nothing at all for the idle
# timer. Silently ineffective is the worst outcome for a feature like this, so
# it is refused loudly at startup instead.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", "host.docker.internal"}


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "").lower()


def _own_public_url() -> str:
    """This service's own public address, as the platform reports it.

    Render sets RENDER_EXTERNAL_URL on every web service. Reading it means the
    keep-alive knows where to find itself without being told, which matters
    because being told is what went wrong: the configured URL named a service
    that had since been renamed and then suspended, and the pings kept landing
    there for hours while this one dozed off every fifteen minutes.
    """
    import os

    return (os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")


def target_url() -> str:
    """Where the ping should actually go.

    An explicit KEEPALIVE_URL wins, but only while it plausibly refers to this
    service. If the platform tells us our own hostname and the configured URL
    disagrees with it, the configured one is stale and pinging it does nothing
    for our idle timer — so we ping ourselves and complain in the log.
    """
    configured = settings.KEEPALIVE_URL.strip()
    own = _own_public_url()
    if configured and own and _host_of(configured) != _host_of(own):
        log.warning(
            "KEEPALIVE_URL points at %r but this service is %r — pinging that host "
            "does nothing for THIS one's idle timer, so using our own address "
            "instead. Update KEEPALIVE_URL to stop this warning.",
            _host_of(configured), _host_of(own))
        return f"{own}/api/health"
    if configured:
        return configured
    return f"{own}/api/health" if own else ""


def configuration_problem() -> str:
    """Why the keep-alive will not run, in words. Empty when it is fine."""
    url = target_url()
    if not url:
        return ""                      # not configured is not a problem
    if not url.startswith(("http://", "https://")):
        return f"KEEPALIVE_URL must be a full http(s) URL, got {url!r}"
    if _host_of(url) in _LOCAL_HOSTS:
        return (f"KEEPALIVE_URL points at {_host_of(url)!r}, which never leaves this "
                "container — set it to the public address of this service instead")
    if settings.KEEPALIVE_INTERVAL_MINUTES >= 15:
        return (f"KEEPALIVE_INTERVAL_MINUTES is {settings.KEEPALIVE_INTERVAL_MINUTES}; "
                "free hosts idle out at about 15 minutes, so use something below that")
    return ""


def enabled() -> bool:
    """Should the loop run at all?"""
    return bool(target_url()) and not configuration_problem()


def ping_once() -> bool:
    """One request to our own public URL. Never raises; returns whether it landed.

    Synchronous on purpose — the caller runs it in a worker thread so a slow
    or hanging network call cannot block the event loop that is serving real
    requests.
    """
    url = target_url()
    if not url:
        return False
    try:
        import httpx

        # trust_env=False: a proxy set in the environment would send this
        # somewhere other than our own host, which defeats the entire point.
        with httpx.Client(timeout=20.0, trust_env=False, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "eaios-keepalive/1"})
        ok = response.status_code < 500
        if not ok:
            log.warning("keep-alive ping returned %s", response.status_code)
        return ok
    except Exception as exc:   # noqa: BLE001 — a failed ping must never disturb the app
        log.warning("keep-alive ping failed: %s", exc)
        return False
