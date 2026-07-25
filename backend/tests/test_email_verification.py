"""Proving that a signup owns the email address it claims.

Before this, anyone could type any address and receive a workspace. These
tests pin both routes to the same guarantee — Google's assertion, or a code
we sent — and pin the things that make a verification system safe rather than
merely present: hashed codes, expiry, attempt limits, and no way to use the
endpoints to discover which addresses are registered.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models import User
from app.services import verification


def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def require_verification(monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)


def _signup(c, company, email, pw="welcome123"):
    return c.post("/api/auth/signup", json={"company_name": company, "full_name": "Owner One",
                                            "email": email, "password": pw})


@pytest.mark.parametrize("env,expected,why", [
    ({}, False, "no provider — a code nobody receives would lock out every signup"),
    ({"RESEND_API_KEY": "re_test"}, True, "Resend configured, so codes are deliverable"),
    ({"SMTP_HOST": "smtp.example.com"}, True, "SMTP configured, so codes are deliverable"),
    ({"REQUIRE_EMAIL_VERIFICATION": "1"}, True, "explicitly demanded, provider or not"),
    ({"REQUIRE_EMAIL_VERIFICATION": "0", "RESEND_API_KEY": "re_test"}, False,
     "explicitly waived, provider or not"),
])
def test_verification_follows_whether_mail_can_actually_be_sent(env, expected, why, monkeypatch):
    """Turning the gate on with nowhere to send codes is an outage, not a
    security control: the code lands in the server log and the person who just
    created a workspace can never get in. So the default follows delivery."""
    from app.core.config import Settings
    # conftest exports these for the suite; this test is about the defaults.
    for k in ("REQUIRE_EMAIL_VERIFICATION", "RESEND_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None, **env)
    assert s.REQUIRE_EMAIL_VERIFICATION is expected, why


def _user(email: str) -> User:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).one()
    finally:
        db.close()


SENT: dict[str, str] = {}


@pytest.fixture(autouse=True)
def capture_codes(monkeypatch):
    """Read the code where a real inbox would — at the send. Nothing else in
    the application ever holds the plaintext, which is the point."""
    from app.api.routes import auth as auth_routes
    from app.services import emailer

    def fake_send(to: str, code: str, company: str) -> bool:
        SENT[to.lower()] = code
        return True

    monkeypatch.setattr(emailer, "send_verification_code", fake_send)
    monkeypatch.setattr(auth_routes.emailer, "send_verification_code", fake_send)
    SENT.clear()
    yield


def _code_for(email: str) -> str:
    code = SENT.get(email.lower())
    assert code, f"no verification code was sent to {email}"
    return code


# ── signup is no longer proof of anything on its own ─────────────────────
@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/auth/config", None),
    ("post", "/api/auth/verify", {"email": "a@b.dev", "code": "123456"}),
    ("post", "/api/auth/verify/resend", {"email": "a@b.dev"}),
])
def test_the_sign_in_screen_works_before_anyone_has_a_token(method, path, body):
    """These three run when the caller has no session — by definition. Putting
    the Google client id behind a bearer token meant the button that starts a
    Google sign-in could only render for someone already signed in."""
    with client() as c:
        r = c.request(method.upper(), path, json=body)
        assert r.status_code != 401, f"{path} demands a token it cannot have yet"


def test_signup_creates_an_unverified_account_and_says_so():
    with client() as c:
        r = _signup(c, "Unverified Co", "owner@unverified.dev")
        assert r.status_code == 201
        body = r.json()
        assert body["email_verified"] is False
        assert body["verification_required"] is True
        assert _user("owner@unverified.dev").email_verified is False


def test_an_unverified_account_cannot_use_the_app():
    """The token issued at signup is real, so this has to be enforced on the
    server — hiding the interface would not be enough."""
    with client() as c:
        h = {"Authorization": "Bearer " + _signup(c, "Gate Co", "owner@gateco.dev")
             .json()["token"]["access_token"]}
        blocked = c.post("/api/users", headers=h, json={
            "email": "x@gateco.dev", "full_name": "X Y", "password": "welcome123", "role": "employee"})
        assert blocked.status_code == 403
        assert "verify your email" in blocked.json()["detail"].lower()
        assert blocked.headers.get("X-Verification-Required") == "1"


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/documents", None),
    ("get", "/api/tasks", None),
    ("get", "/api/auth/me", None),
    ("post", "/api/chat", {"message": "hello"}),
])
def test_every_authenticated_route_is_gated_not_just_the_admin_ones(method, path, body):
    """Caught in a browser: the gate was on the role guard, so an unverified
    account was shown a verification screen while its token could still read
    and write documents. The check belongs where the user is loaded."""
    who = f"owner@{path.strip('/').replace('/', '-')}.dev"   # one account per case
    with client() as c:
        h = {"Authorization": "Bearer " + _signup(c, "Everywhere Co", who)
             .json()["token"]["access_token"]}
        r = c.request(method.upper(), path, headers=h, json=body)
        assert r.status_code == 403, f"{method.upper()} {path} let an unverified account through"
        assert r.headers.get("X-Verification-Required") == "1"


def test_the_right_code_verifies_and_unlocks_the_app():
    with client() as c:
        h = {"Authorization": "Bearer " + _signup(c, "Unlock Co", "owner@unlockco.dev")
             .json()["token"]["access_token"]}
        code = _code_for("owner@unlockco.dev")

        r = c.post("/api/auth/verify", json={"email": "owner@unlockco.dev", "code": code})
        assert r.status_code == 200 and r.json()["email_verified"] is True

        assert c.post("/api/users", headers=h, json={
            "email": "y@unlockco.dev", "full_name": "Y Z",
            "password": "welcome123", "role": "employee"}).status_code == 201


# ── the properties that make it real security ────────────────────────────
def test_the_code_is_never_stored_in_plaintext():
    with client() as c:
        _signup(c, "Hash Co", "owner@hashco.dev")
        u = _user("owner@hashco.dev")
        code = _code_for("owner@hashco.dev")
        assert u.verify_code_hash and code not in u.verify_code_hash
        assert len(u.verify_code_hash) >= 40


def test_a_wrong_code_is_refused_and_counted():
    with client() as c:
        _signup(c, "Attempts Co", "owner@attempts.dev")
        for _ in range(3):
            r = c.post("/api/auth/verify", json={"email": "owner@attempts.dev", "code": "000000"})
            assert r.status_code == 400
        assert _user("owner@attempts.dev").verify_attempts >= 3
        assert _user("owner@attempts.dev").email_verified is False


def test_guessing_is_cut_off_after_a_handful_of_tries():
    with client() as c:
        _signup(c, "Bruteforce Co", "owner@brute.dev")
        real = _code_for("owner@brute.dev")
        for _ in range(verification.MAX_ATTEMPTS):
            c.post("/api/auth/verify", json={"email": "owner@brute.dev", "code": "111111"})
        # even the correct code is refused once the limit is hit
        r = c.post("/api/auth/verify", json={"email": "owner@brute.dev", "code": real})
        assert r.status_code == 400 and "too many" in r.json()["detail"].lower()


def test_an_expired_code_is_refused():
    with client() as c:
        _signup(c, "Expiry Co", "owner@expiry.dev")
        code = _code_for("owner@expiry.dev")
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.email == "owner@expiry.dev").one()
            u.verify_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()
        r = c.post("/api/auth/verify", json={"email": "owner@expiry.dev", "code": code})
        assert r.status_code == 400 and "expired" in r.json()["detail"].lower()


def test_a_code_cannot_be_replayed_against_a_different_account():
    """Codes are bound to their address, so intercepting one is useless
    elsewhere."""
    with client() as c:
        _signup(c, "Bind A", "a@bindco.dev")
        _signup(c, "Bind B", "b@bindco.dev")
        code_a = _code_for("a@bindco.dev")
        r = c.post("/api/auth/verify", json={"email": "b@bindco.dev", "code": code_a})
        assert r.status_code == 400
        assert _user("b@bindco.dev").email_verified is False


def test_resend_issues_a_new_code_and_clears_failed_attempts():
    with client() as c:
        _signup(c, "Resend Co", "owner@resendco.dev")
        first = _code_for("owner@resendco.dev")
        c.post("/api/auth/verify", json={"email": "owner@resendco.dev", "code": "000000"})
        assert c.post("/api/auth/verify/resend",
                      json={"email": "owner@resendco.dev"}).status_code == 200
        second = _code_for("owner@resendco.dev")
        assert second != first or _user("owner@resendco.dev").verify_attempts == 0
        assert c.post("/api/auth/verify", json={"email": "owner@resendco.dev",
                                                "code": second}).status_code == 200


# ── no account enumeration through these endpoints ───────────────────────
def test_verifying_an_unknown_address_looks_the_same_as_a_wrong_code():
    with client() as c:
        r = c.post("/api/auth/verify", json={"email": "nobody@nowhere.dev", "code": "123456"})
        assert r.status_code == 400
        assert "isn't right" in r.json()["detail"].lower()
        assert "not found" not in r.text.lower() and "no account" not in r.text.lower()


def test_resend_never_reveals_whether_an_address_is_registered():
    with client() as c:
        _signup(c, "Known Co", "known@knownco.dev")
        a = c.post("/api/auth/verify/resend", json={"email": "known@knownco.dev"})
        b = c.post("/api/auth/verify/resend", json={"email": "ghost@nowhere.dev"})
        assert a.status_code == b.status_code == 200
        assert a.json() == b.json()


# ── disposable addresses ─────────────────────────────────────────────────
@pytest.mark.parametrize("email", ["x@mailinator.com", "y@guerrillamail.com", "z@yopmail.com"])
def test_throwaway_inboxes_are_refused(email):
    with client() as c:
        r = _signup(c, "Temp Co", email)
        assert r.status_code == 422
        assert "permanent" in r.json()["detail"].lower()


def test_a_company_domain_is_accepted():
    """The customers this product is for do NOT sign up from @gmail.com."""
    with client() as c:
        assert _signup(c, "Northwind Legal", "partner@northwindlegal.co.uk").status_code == 201


# ── Google sign-in ───────────────────────────────────────────────────────
def test_google_token_must_be_issued_for_this_app(monkeypatch):
    """A token minted for a different Google application must be refused —
    otherwise anyone with any Google app could sign in as anyone."""
    from app.services import google_auth

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "our-client-id.apps.googleusercontent.com")

    class FakeResponse:
        status_code = 200
        @staticmethod
        def json():
            return {"aud": "SOMEONE-ELSES-app.apps.googleusercontent.com",
                    "iss": "accounts.google.com", "email": "victim@corp.dev",
                    "email_verified": "true", "name": "Victim"}

    monkeypatch.setattr(google_auth.httpx if hasattr(google_auth, "httpx") else google_auth,
                        "__name__", "app.services.google_auth", raising=False)
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())

    with pytest.raises(google_auth.GoogleAuthError) as err:
        google_auth.verify_id_token("x" * 40)
    assert "issued for this app" in str(err.value)


def test_google_requires_a_verified_address(monkeypatch):
    from app.services import google_auth

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "our-client-id.apps.googleusercontent.com")

    class FakeResponse:
        status_code = 200
        @staticmethod
        def json():
            return {"aud": "our-client-id.apps.googleusercontent.com",
                    "iss": "accounts.google.com", "email": "unconfirmed@corp.dev",
                    "email_verified": "false", "name": "Nope"}

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse())
    with pytest.raises(google_auth.GoogleAuthError):
        google_auth.verify_id_token("x" * 40)


def test_google_signup_is_verified_immediately(monkeypatch):
    """No code to send: Google already asserted the address."""
    from app.services import google_auth

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "our-client-id.apps.googleusercontent.com")
    from app.api.routes import auth as auth_routes
    fake = lambda _t: {"email": "founder@acmeworkspace.dev", "name": "Founder",
                       "sub": "1", "hd": "acmeworkspace.dev"}
    monkeypatch.setattr(google_auth, "verify_id_token", fake)
    monkeypatch.setattr(auth_routes, "verify_id_token", fake)   # bound at import
    with client() as c:
        r = c.post("/api/auth/google", json={"credential": "y" * 40,
                                             "company_name": "Acme Workspace"})
        assert r.status_code == 200, r.text
        assert r.json()["email_verified"] is True
        assert r.json()["org"]["name"] == "Acme Workspace"
        # and the app is usable at once
        h = {"Authorization": "Bearer " + r.json()["token"]["access_token"]}
        assert c.get("/api/documents", headers=h).status_code == 200


def test_google_signin_for_an_unknown_account_does_not_invent_a_workspace(monkeypatch):
    from app.services import google_auth

    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cid")
    from app.api.routes import auth as auth_routes
    fake = lambda _t: {"email": "stranger@elsewhere.dev", "name": "Stranger", "sub": "2", "hd": ""}
    monkeypatch.setattr(google_auth, "verify_id_token", fake)
    monkeypatch.setattr(auth_routes, "verify_id_token", fake)
    with client() as c:
        r = c.post("/api/auth/google", json={"credential": "z" * 40})
        assert r.status_code == 404 and "create one first" in r.json()["detail"].lower()


# ── existing customers are not locked out ────────────────────────────────
def test_accounts_that_predate_verification_still_work():
    """The migration grandfathers them: retro-locking real users out would be
    worse than the gap it closes."""
    with client() as c:
        r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
        assert r.status_code == 200
        assert r.json()["email_verified"] is True
