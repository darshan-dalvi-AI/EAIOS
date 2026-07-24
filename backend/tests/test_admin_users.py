"""Admin user management — create teammate ('hire'), RBAC, login as the new user."""
from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c, email="admin@eaios.dev", pw="admin12345") -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


def test_admin_creates_user_who_can_log_in():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/users", headers=h, json={
            "email": "New.Hire@Test.dev", "full_name": "New Hire",
            "password": "welcome123", "role": "manager"})
        assert r.status_code == 201
        body = r.json()
        assert body["email"] == "new.hire@test.dev"   # normalized lower-case
        assert body["role"] == "manager"

        # the new person can sign in with the credentials the admin set
        login = c.post("/api/auth/login", json={"email": "new.hire@test.dev", "password": "welcome123"})
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "manager"

        # appears in the admin user list
        assert any(u["email"] == "new.hire@test.dev" for u in c.get("/api/users", headers=h).json())


def test_duplicate_and_bad_role_rejected():
    with client() as c:
        h = _headers(c)
        assert c.post("/api/users", headers=h, json={"email": "admin@eaios.dev",
                      "full_name": "Dupe", "password": "welcome123", "role": "employee"}).status_code == 409
        assert c.post("/api/users", headers=h, json={"email": "x@test.dev",
                      "full_name": "Bad Role", "password": "welcome123", "role": "superuser"}).status_code == 422


def test_non_admin_cannot_create_users():
    with client() as c:
        c.post("/api/auth/register", json={"email": "emp_hr@test.dev", "password": "demo12345", "full_name": "Emp HR"})
        he = _headers(c, "emp_hr@test.dev", "demo12345")
        r = c.post("/api/users", headers=he, json={"email": "z@test.dev",
                   "full_name": "Blocked", "password": "welcome123", "role": "employee"})
        assert r.status_code == 403
