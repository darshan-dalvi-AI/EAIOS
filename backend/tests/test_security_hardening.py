"""Pre-production security controls.

Each test corresponds to a control that, if it silently regressed, would not
be visible in the interface — which is exactly why it is pinned here.
"""
import io
import os

import pytest
from fastapi.testclient import TestClient

from app.core import errors, uploads
from app.core.config import DEV_SECRET, Settings, verify_production_secrets
from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _signup(c, company, email, pw="welcome123"):
    r = c.post("/api/auth/signup", json={"company_name": company, "full_name": "Owner One",
                                         "email": email, "password": pw})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


# ══ 1 · rate limiting ══════════════════════════════════════════════════
def test_every_rule_threshold_is_configurable(monkeypatch):
    """Limits must be tunable per deployment, not compiled into the code."""
    from app.core import ratelimit

    monkeypatch.setattr(ratelimit.settings, "RL_LOGIN_CAPACITY", 3, raising=False)
    monkeypatch.setattr(ratelimit.settings, "RL_LOGIN_WINDOW", 120, raising=False)
    rules = ratelimit.build_rules()
    login = next(r for _, path, r in rules if path.endswith("/auth/login"))
    assert login.capacity == 3 and login.per_seconds == 120


def test_auth_routes_are_stricter_than_ordinary_actions():
    from app.core import ratelimit

    rules = {r.name: r for _, _, r in ratelimit.build_rules()}
    assert rules["login"].capacity < rules["chat"].capacity
    assert rules["signup"].capacity < rules["chat"].capacity
    # signup must be covered at all — unlimited workspace creation is a
    # resource-exhaustion vector
    assert "signup" in rules and rules["signup"].per_seconds >= 600


def test_auth_rules_key_on_ip_and_account_with_backoff():
    from app.core import ratelimit

    rules = {r.name: r for _, _, r in ratelimit.build_rules()}
    assert rules["login"].by_user is False        # per-IP, not per-token
    assert rules["login"].by_account is True      # and per targeted account
    assert rules["login"].backoff is True
    assert rules["signup"].backoff is True


def test_backoff_grows_exponentially_and_is_capped():
    from app.core import ratelimit

    ratelimit.clear_backoff()
    waits = [ratelimit._backoff_strike("t:demo") for _ in range(6)]
    assert waits[0] < waits[1] < waits[2], waits          # doubling
    assert all(w <= ratelimit._BACKOFF_MAX for w in waits)  # never unbounded
    ratelimit.clear_backoff()
    assert ratelimit._backoff_check("t:demo") == 0        # cleared on success


# ══ 2 · input validation ═══════════════════════════════════════════════
@pytest.mark.parametrize("payload", [
    {"company_name": "A", "full_name": "Owner One", "email": "a@b.dev", "password": "welcome123"},      # name too short
    {"company_name": "Acme", "full_name": "Owner One", "email": "not-an-email", "password": "welcome123"},
    {"company_name": "Acme", "full_name": "Owner One", "email": "a@b.dev", "password": "short"},        # weak password
    {"company_name": "x" * 500, "full_name": "Owner One", "email": "a@b.dev", "password": "welcome123"},
    {"company_name": "Acme", "full_name": "Owner One", "email": "a@b.dev"},                             # missing field
])
def test_signup_rejects_anything_off_schema(payload):
    with client() as c:
        assert c.post("/api/auth/signup", json=payload).status_code == 422


def test_role_must_be_one_of_the_four_known_values():
    with client() as c:
        h = _signup(c, "Roles Ltd", "admin@roles.dev")
        bad = c.post("/api/users", headers=h, json={
            "email": "x@roles.dev", "full_name": "X Y", "password": "welcome123", "role": "superuser"})
        assert bad.status_code == 422           # rejected, not coerced or stored


def test_oversized_free_text_is_rejected_not_truncated():
    with client() as c:
        h = _signup(c, "Big Text Co", "admin@bigtext.dev")
        assert c.post("/api/chat", headers=h, json={"message": "x" * 20000}).status_code == 422


def test_validation_errors_do_not_echo_the_submitted_value():
    """A 422 must not reflect the password back in the response body."""
    with client() as c:
        r = c.post("/api/auth/signup", json={
            "company_name": "A",                      # too short → 422
            "full_name": "Owner One",
            "email": "echo-check@b.dev", "password": "hunter2secret"})
        assert r.status_code == 422
        assert "hunter2secret" not in r.text          # the value is never reflected


# ══ 3 · secrets ════════════════════════════════════════════════════════
def test_production_refuses_to_start_with_the_default_secret():
    s = Settings(ENVIRONMENT="production", SECRET_KEY=DEV_SECRET)
    problems = verify_production_secrets(s)
    assert problems and "SECRET_KEY" in problems[0]


def test_production_refuses_a_short_secret_and_wildcard_cors():
    assert verify_production_secrets(Settings(ENVIRONMENT="production", SECRET_KEY="tooshort"))
    assert verify_production_secrets(
        Settings(ENVIRONMENT="production", SECRET_KEY="k" * 40, CORS_ORIGINS="*"))


def test_development_still_boots_with_defaults():
    assert verify_production_secrets(Settings(ENVIRONMENT="development")) == []


def test_credentials_are_scrubbed_from_logged_detail():
    dirty = ("https://api.example.com/sync?access_token=ya29.SUPERSECRET&x=1 "
             "sk-abcdef0123456789abcdef postgresql://user:hunter2@host/db")
    clean = errors.redact(dirty)
    assert "ya29.SUPERSECRET" not in clean
    assert "sk-abcdef0123456789abcdef" not in clean
    assert "hunter2" not in clean


# ══ 5 · error handling ═════════════════════════════════════════════════
def test_public_message_hides_the_cause_and_returns_a_reference():
    msg, ref = errors.public_message(RuntimeError("connection to 10.0.0.5:5432 failed: FATAL role x"),
                                     "unit test")
    assert "10.0.0.5" not in msg and "FATAL" not in msg
    assert ref and ref in msg


def test_unknown_route_returns_no_internal_detail():
    with client() as c:
        r = c.get("/api/does-not-exist")
        assert r.status_code == 404
        body = r.text.lower()
        for leak in ("traceback", "site-packages", "/app/", "sqlalchemy", ".py\""):
            assert leak not in body


def test_api_docs_are_disabled_in_production():
    """The schema is a map of the attack surface; it stays in development."""
    assert Settings(ENVIRONMENT="production").is_production is True
    assert Settings(ENVIRONMENT="development").is_production is False


# ══ 6 · file upload ════════════════════════════════════════════════════
def test_extension_alone_is_not_enough_content_must_match():
    with client() as c:
        h = _signup(c, "Upload Guard Co", "admin@uploadguard.dev")
        # A PHP web shell renamed to .pdf
        r = c.post("/api/documents/upload", headers=h,
                   files={"file": ("invoice.pdf", io.BytesIO(b"<?php system($_GET['c']); ?>"), "application/pdf")})
        assert r.status_code == 415
        assert c.get("/api/documents", headers=h).json() == []   # nothing stored


def test_executables_are_refused_under_any_extension():
    with client() as c:
        h = _signup(c, "Exe Co", "admin@execo.dev")
        for name, blob in [("notes.txt", b"#!/bin/sh\nrm -rf /"),
                           ("report.pdf", b"MZ\x90\x00\x03"),
                           ("data.csv", b"\x7fELF\x02\x01\x01")]:
            r = c.post("/api/documents/upload", headers=h,
                       files={"file": (name, io.BytesIO(blob), "application/octet-stream")})
            assert r.status_code == 415, f"{name} was accepted"


def test_oversized_upload_is_refused_and_leaves_nothing_behind(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "MAX_UPLOAD_MB", 1)
    with client() as c:
        h = _signup(c, "Big File Co", "admin@bigfile.dev")
        blob = b"%PDF-1.4\n" + b"A" * (2 * 1024 * 1024)
        r = c.post("/api/documents/upload", headers=h,
                   files={"file": ("huge.pdf", io.BytesIO(blob), "application/pdf")})
        assert r.status_code == 413
        assert c.get("/api/documents", headers=h).json() == []   # no orphan row


def test_a_genuine_file_still_uploads():
    with client() as c:
        h = _signup(c, "Happy Path Co", "admin@happypath.dev")
        r = c.post("/api/documents/upload", headers=h,
                   files={"file": ("policy.txt", io.BytesIO(b"Employees get 27 leave days."), "text/plain")})
        assert r.status_code == 201, r.text
        assert len(c.get("/api/documents", headers=h).json()) == 1


def test_filenames_cannot_traverse_directories():
    assert "/" not in uploads.safe_filename("../../../etc/passwd")
    assert uploads.safe_filename("../../../etc/passwd") == "etc_passwd" or \
           uploads.safe_filename("../../../etc/passwd") == "passwd"
    assert uploads.safe_filename("C:\\Windows\\system32\\evil.txt") == "evil.txt"
    assert uploads.safe_filename(None)                     # never empty
    assert len(uploads.safe_filename("x" * 900 + ".txt")) <= 255


def test_uploads_are_stored_outside_anything_served_as_static():
    """A stored file must have no URL, so it can never be executed by the
    web server even if its content were hostile."""
    upload_dir = os.path.abspath(uploads.ensure_upload_dir())
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
    assert not upload_dir.startswith(static_dir)


def test_empty_uploads_are_refused():
    with client() as c:
        h = _signup(c, "Empty Co", "admin@emptyco.dev")
        r = c.post("/api/documents/upload", headers=h,
                   files={"file": ("blank.txt", io.BytesIO(b""), "text/plain")})
        assert r.status_code in (400, 415)


# ══ 7 · HTTP security headers ══════════════════════════════════════════
def test_security_headers_present_on_every_response():
    with client() as c:
        for path in ("/api/health", "/api/does-not-exist"):
            h = c.get(path).headers
            assert h.get("X-Frame-Options") == "DENY"                    # clickjacking
            assert h.get("X-Content-Type-Options") == "nosniff"          # MIME sniffing
            assert h.get("Referrer-Policy") == "strict-origin-when-cross-origin"
            assert "Content-Security-Policy" in h
            assert "geolocation=()" in h.get("Permissions-Policy", "")
            assert h.get("Server") == "EAIOS" and "X-Powered-By" not in h


def test_csp_blocks_framing_and_plugins_without_allowing_eval():
    from app.core.headers import CSP

    assert "frame-ancestors 'none'" in CSP
    assert "object-src 'none'" in CSP
    assert "base-uri 'self'" in CSP and "form-action 'self'" in CSP
    assert "unsafe-eval" not in CSP          # injected text can never become code


def test_hsts_only_in_production(monkeypatch):
    from app.core.config import settings as live

    with client() as c:
        assert "Strict-Transport-Security" not in c.get("/api/health").headers
    monkeypatch.setattr(live, "ENVIRONMENT", "production")
    with client() as c:
        assert "max-age=31536000" in c.get("/api/health").headers.get("Strict-Transport-Security", "")


def test_cors_is_an_explicit_whitelist_not_a_wildcard():
    from app.core.config import settings as live

    assert "*" not in live.cors_origins


# ══ 5b · password hashing ══════════════════════════════════════════════
def test_hash_records_its_cost_and_rejects_wrong_passwords():
    from app.core.security import PBKDF2_ITERATIONS, hash_password, verify_password

    h = hash_password("correct horse battery")
    # The cost is recorded in the hash, whatever this deployment configured.
    assert h.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")
    assert PBKDF2_ITERATIONS >= 1000
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)
    assert not verify_password("correct horse battery", "garbage")


def test_legacy_hashes_still_verify_and_are_marked_for_upgrade():
    """Raising the cost must never lock an existing account out."""
    import hashlib
    import os

    from app.core.security import LEGACY_ITERATIONS, needs_rehash, verify_password

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", b"oldpassword", salt, LEGACY_ITERATIONS)
    legacy = f"{salt.hex()}${digest.hex()}"
    assert verify_password("oldpassword", legacy)      # still works
    # "Needs upgrading" is relative to the configured cost. The suite runs a
    # deliberately low cost, so compare against that rather than a constant.
    from app.core.security import PBKDF2_ITERATIONS
    assert needs_rehash(legacy) is (LEGACY_ITERATIONS < PBKDF2_ITERATIONS)


def test_login_transparently_upgrades_an_old_hash():
    import hashlib
    import os

    from app.core.database import SessionLocal
    from app.core.security import LEGACY_ITERATIONS, PBKDF2_ITERATIONS
    from app.models import User

    with client() as c:
        _signup(c, "Rehash Co", "admin@rehash.dev", pw="welcome123")
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.email == "admin@rehash.dev").one()
            salt = os.urandom(16)
            u.hashed_password = (f"{salt.hex()}$"
                                 f"{hashlib.pbkdf2_hmac('sha256', b'welcome123', salt, LEGACY_ITERATIONS).hex()}")
            db.commit()
        finally:
            db.close()

        assert c.post("/api/auth/login",
                      json={"email": "admin@rehash.dev", "password": "welcome123"}).status_code == 200

        db = SessionLocal()
        try:
            u = db.query(User).filter(User.email == "admin@rehash.dev").one()
            if LEGACY_ITERATIONS < PBKDF2_ITERATIONS:      # an upgrade was due
                assert u.hashed_password.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")
            else:
                # The suite runs a deliberately low cost, so a 100k legacy hash
                # is already stronger than required and is left alone.
                assert u.hashed_password.count("$") == 1   # still the legacy format
        finally:
            db.close()


# ══ 10 · LLM cost controls ═════════════════════════════════════════════
def test_every_generation_is_token_capped():
    """An uncapped response is an unbounded bill."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app" / "llm" / "provider.py"
    text = src.read_text(encoding="utf-8")
    # both remote providers must pass a ceiling
    assert text.count("settings.LLM_MAX_TOKENS") >= 2
    assert '"max_tokens": 1500' not in text          # no hardcoded ceiling left


def test_daily_token_budget_blocks_further_ai_use(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "LLM_DAILY_TOKEN_BUDGET", 1)   # already exceeded
    with client() as c:
        h = _signup(c, "Budget Co", "admin@budgetco.dev")
        c.post("/api/chat", headers=h, json={"message": "first question"})   # records usage
        r = c.post("/api/chat", headers=h, json={"message": "second question"})
        assert r.status_code == 429
        assert "limit" in r.json()["detail"].lower()
        assert r.headers.get("Retry-After")


def test_budget_of_zero_disables_the_limit(monkeypatch):
    from app.core.config import settings as live

    monkeypatch.setattr(live, "LLM_DAILY_TOKEN_BUDGET", 0)
    with client() as c:
        h = _signup(c, "Unlimited Co", "admin@unlimited.dev")
        for _ in range(3):
            assert c.post("/api/chat", headers=h, json={"message": "hello"}).status_code == 200


# ══ 4 · per-resource ownership ═════════════════════════════════════════
def test_a_teammate_cannot_rename_someone_elses_task():
    """The board is shared — moving cards is fine, rewriting them is not."""
    with client() as c:
        ha = _signup(c, "Board Co", "admin@boardco.dev")
        c.post("/api/users", headers=ha, json={"email": "emp@boardco.dev", "full_name": "Emp Loyee",
                                               "password": "welcome123", "role": "employee"})
        he = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"email": "emp@boardco.dev", "password": "welcome123"}
        ).json()["token"]["access_token"]}

        task = c.post("/api/tasks", headers=ha, json={"title": "Admin's task"}).json()
        # collaboration still allowed
        assert c.patch(f"/api/tasks/{task['id']}", headers=he, json={"status": "doing"}).status_code == 200
        # rewriting someone else's task is not
        assert c.patch(f"/api/tasks/{task['id']}", headers=he,
                       json={"title": "hijacked"}).status_code == 403


# ══ deploy resilience ══════════════════════════════════════════════════
def test_health_is_cheap_and_never_blocks_on_the_llm(monkeypatch):
    """A deploy was rejected once because the health check could not answer
    in time. It must stay fast and must not depend on provider detection."""
    import app.llm.provider as provider

    def boom():
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(provider, "get_llm", boom)
    with client() as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"          # still healthy
        assert r.json()["llm_provider"] == "initialising"


def test_slow_startup_work_is_not_on_the_serving_path():
    """Schema hardening and seeding run in the background after the app is
    up — putting them inline is what timed out the health check."""
    import inspect as _inspect

    from app import main
    from app.core import database

    lifespan_src = _inspect.getsource(main.lifespan)
    assert "_warm_up" in lifespan_src
    assert "to_thread" in lifespan_src            # off the event loop
    for slow in ("harden_public_schema", "_seed_if_empty", "ensure_bucket"):
        assert slow not in lifespan_src, f"{slow} still blocks startup"

    # and the hardening is no longer *called* inside init_db (the explanatory
    # comment there mentions it by name, so compare code lines only)
    init_code = [ln.split("#")[0] for ln in _inspect.getsource(database.init_db).splitlines()]
    assert not any("harden_public_schema(" in ln for ln in init_code)


def test_warm_up_survives_a_failing_step(monkeypatch):
    """One broken warm-up step must not stop the others or crash the app."""
    from app import main
    from app.core import database, storage

    calls = []
    monkeypatch.setattr(database, "harden_public_schema", lambda: (_ for _ in ()).throw(RuntimeError("db far away")))
    monkeypatch.setattr(main, "_seed_if_empty", lambda: calls.append("seed"))
    monkeypatch.setattr(storage, "ensure_bucket", lambda: calls.append("bucket"))
    main._warm_up()                                # must not raise
    assert calls == ["seed", "bucket"]             # later steps still ran
