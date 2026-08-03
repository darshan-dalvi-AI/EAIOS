"""The keep-alive must ping THIS service, not one it used to be called.

Render's free plan suspends a service after ~15 minutes without inbound
traffic. The app keeps itself awake by requesting its own public URL on a
timer, which leaves the container and returns through the platform's router as
real inbound traffic.

The failure this guards against is the one that happened: KEEPALIVE_URL was
set to a sibling service's address. When that service was renamed and later
suspended, the pings kept going out every ten minutes, kept succeeding at the
HTTP level for a while, and did precisely nothing for this service's idle
timer. Nothing failed. The site simply went to sleep on schedule and nobody
could see why, because the feature responsible was running perfectly.

So the address is no longer taken on trust: RENDER_EXTERNAL_URL is what the
platform says this service is, and a configured URL that disagrees with it is
stale by definition.
"""
import importlib

import pytest

from app.core.config import settings


@pytest.fixture
def keepalive(monkeypatch):
    """A fresh import each time — the module reads os.environ at call time."""
    mod = importlib.import_module("app.services.keepalive")
    return importlib.reload(mod)


def test_uses_our_own_address_when_nothing_is_configured(keepalive, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://k-os.onrender.com")
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "", raising=False)
    assert keepalive.target_url() == "https://k-os.onrender.com/api/health"


def test_a_stale_url_naming_another_service_is_overridden(keepalive, monkeypatch):
    """The exact bug: configured for eaios, deployed as k-os."""
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://k-os.onrender.com")
    monkeypatch.setattr(settings, "KEEPALIVE_URL",
                        "https://eaios.onrender.com/api/health", raising=False)
    assert keepalive.target_url() == "https://k-os.onrender.com/api/health", (
        "a URL pointing at a different host does nothing for this service's "
        "idle timer and must not be used"
    )


def test_a_matching_url_is_left_alone(keepalive, monkeypatch):
    """Overriding the path on our own host stays legitimate."""
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://k-os.onrender.com")
    monkeypatch.setattr(settings, "KEEPALIVE_URL",
                        "https://k-os.onrender.com/api/health", raising=False)
    assert keepalive.target_url() == "https://k-os.onrender.com/api/health"


def test_localhost_is_still_refused(keepalive, monkeypatch):
    """A ping that never leaves the container cannot reset the idle timer."""
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "http://localhost:8000/api/health",
                        raising=False)
    assert "never leaves this container" in keepalive.configuration_problem()
    assert keepalive.enabled() is False


def test_interval_must_beat_the_idle_timeout(keepalive, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://k-os.onrender.com")
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "", raising=False)
    monkeypatch.setattr(settings, "KEEPALIVE_INTERVAL_MINUTES", 20, raising=False)
    assert "idle out at about 15 minutes" in keepalive.configuration_problem()
    assert keepalive.enabled() is False


def test_off_when_there_is_no_public_address_at_all(keepalive, monkeypatch):
    """Local development must not make surprise outbound requests."""
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setattr(settings, "KEEPALIVE_URL", "", raising=False)
    assert keepalive.target_url() == ""
    assert keepalive.enabled() is False
