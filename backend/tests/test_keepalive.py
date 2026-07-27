"""The self-ping that keeps a free-tier host awake.

The whole feature is a workaround for someone else's idle timer, so the thing
worth testing is not that it makes an HTTP request — it is that it fails
*visibly* rather than quietly. A keep-alive that appears configured but does
nothing is worse than none at all: the site still sleeps, and you stop looking
for the reason.
"""
import pytest

from app.core.config import settings
from app.services import keepalive


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "")
    monkeypatch.setattr(settings, "KEEPALIVE_INTERVAL_MINUTES", 10)
    yield


def test_off_unless_a_url_is_configured():
    """Local development and self-hosted installs must never make surprise
    outbound requests just because the code exists."""
    assert keepalive.enabled() is False
    assert keepalive.configuration_problem() == ""      # unset is not an error
    assert keepalive.ping_once() is False               # and does nothing


def test_on_once_a_public_url_is_set(monkeypatch):
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "https://eaios.onrender.com/api/health")
    assert keepalive.enabled() is True
    assert keepalive.configuration_problem() == ""


@pytest.mark.parametrize("url", [
    "http://localhost:8000/api/health",
    "http://127.0.0.1:8000/api/health",
    "http://0.0.0.0:8000/api/health",
    "http://[::1]:8000/api/health",
    "http://host.docker.internal:8000/api/health",
])
def test_a_localhost_url_is_refused(monkeypatch, url):
    """This is the trap the feature exists to avoid. Pinging yourself over the
    loopback interface succeeds, looks healthy in the logs, and does nothing at
    all for the idle timer — the request never reaches the platform's router."""
    monkeypatch.setattr(settings, "KEEPALIVE_URL", url)
    problem = keepalive.configuration_problem()
    assert problem, f"{url} was accepted but can never keep anything awake"
    assert "never leaves this container" in problem
    assert keepalive.enabled() is False


def test_a_url_that_is_not_a_url_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "eaios.onrender.com/api/health")
    assert "full http(s) URL" in keepalive.configuration_problem()
    assert keepalive.enabled() is False


def test_an_interval_longer_than_the_idle_timeout_is_refused(monkeypatch):
    """Pinging every 20 minutes on a host that sleeps at 15 keeps nothing
    awake; it just wakes the service up occasionally, which is what already
    happens without any of this."""
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "https://eaios.onrender.com/api/health")
    monkeypatch.setattr(settings, "KEEPALIVE_INTERVAL_MINUTES", 20)
    assert "idle out" in keepalive.configuration_problem()
    assert keepalive.enabled() is False

    monkeypatch.setattr(settings, "KEEPALIVE_INTERVAL_MINUTES", 10)
    assert keepalive.enabled() is True


def test_a_failed_ping_is_swallowed(monkeypatch):
    """Nothing depends on the result. If the network is down the app carries
    on; the only consequence is that the host may sleep, which is where it
    started."""
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "https://eaios.onrender.com/api/health")

    class Boom:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): raise OSError("network unreachable")

    import httpx
    monkeypatch.setattr(httpx, "Client", Boom)
    assert keepalive.ping_once() is False        # returns, does not raise


def test_a_successful_ping_reports_success(monkeypatch):
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "https://eaios.onrender.com/api/health")
    seen = {}

    class Ok:
        def __init__(self, *a, **k): seen["client_kwargs"] = k
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, **k):
            seen["url"] = url
            return type("R", (), {"status_code": 200})()

    import httpx
    monkeypatch.setattr(httpx, "Client", Ok)
    assert keepalive.ping_once() is True
    assert seen["url"] == "https://eaios.onrender.com/api/health"
    # A proxy from the environment would send this somewhere that is not us,
    # which defeats the point entirely.
    assert seen["client_kwargs"].get("trust_env") is False
    assert seen["client_kwargs"].get("timeout")


def test_a_server_error_counts_as_a_failed_ping(monkeypatch):
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "https://eaios.onrender.com/api/health")

    class Broken:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *a, **k): return type("R", (), {"status_code": 503})()

    import httpx
    monkeypatch.setattr(httpx, "Client", Broken)
    assert keepalive.ping_once() is False


def test_the_loop_is_independent_of_the_workflow_scheduler():
    """They solve unrelated problems. Turning workflow scheduling off must not
    quietly stop the thing keeping the site reachable."""
    import inspect

    from app import main

    assert hasattr(main, "_keepalive_loop")
    source = inspect.getsource(main.lifespan)
    assert "keepalive.enabled()" in source
    # the keep-alive task must not be created inside the scheduler branch
    assert "_keepalive_loop()) if keepalive.enabled()" in source
