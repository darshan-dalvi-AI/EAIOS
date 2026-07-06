"""Rate limiting: bucket math, rule matching, middleware 429 behavior."""
import time

from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.ratelimit import Rule, _match, _MemoryBuckets
from app.main import app


def test_token_bucket_refills():
    buckets = _MemoryBuckets()
    rule = Rule("t", capacity=2, per_seconds=1)  # 2 tokens/sec
    assert buckets.allow("k", rule) == (True, 0)
    assert buckets.allow("k", rule)[0] is True
    ok, retry = buckets.allow("k", rule)
    assert ok is False and retry >= 1
    time.sleep(0.6)  # > one token refilled
    assert buckets.allow("k", rule)[0] is True


def test_rule_matching():
    assert _match("POST", "/api/auth/login").name == "login"
    assert _match("POST", "/api/chat").name == "chat"
    assert _match("POST", "/api/workflows/abc123/run").name == "wf-run"
    assert _match("GET", "/api/chat") is None
    assert _match("POST", "/api/health") is None


def test_middleware_returns_429(monkeypatch):
    tiny = Rule("test-tiny", capacity=2, per_seconds=3600, by_user=False)
    monkeypatch.setattr(ratelimit, "RULES", [("POST", "/api/auth/login", tiny)])
    with TestClient(app) as c:
        body = {"email": "nobody@x.dev", "password": "wrong"}
        r1 = c.post("/api/auth/login", json=body)
        r2 = c.post("/api/auth/login", json=body)
        assert r1.status_code == 401 and r2.status_code == 401  # limited, not blocked
        r3 = c.post("/api/auth/login", json=body)
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
        assert "Rate limit" in r3.json()["detail"]


def test_disabled_flag_bypasses(monkeypatch):
    from app.core.config import settings

    tiny = Rule("test-off", capacity=1, per_seconds=3600, by_user=False)
    monkeypatch.setattr(ratelimit, "RULES", [("POST", "/api/auth/login", tiny)])
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    with TestClient(app) as c:
        body = {"email": "nobody@x.dev", "password": "wrong"}
        for _ in range(4):
            assert c.post("/api/auth/login", json=body).status_code == 401
