"""The first-admin bootstrap must never hand a public deployment a login
that anyone can use.

``admin@eaios.dev`` / ``admin12345`` is convenient on a laptop and a breach on
a public URL: the password is in this repository, so anyone who reads it can
sign in as an administrator. These tests pin the two guarantees of the fix —
production never *creates* that account, and a build that already did has its
password rotated on the next boot — while leaving the development convenience
intact.

The bootstrap deletes and creates users, so these tests run against a database
of their OWN (a temp SQLite that main.SessionLocal is pointed at) rather than
the one the rest of the suite shares — otherwise clearing users here would pull
the shared admin out from under every other test.
"""
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main
from app.core import database as db_module
from app.core.security import verify_password
from app.models import User


@pytest.fixture
def own_database(monkeypatch):
    """A throwaway database that _bootstrap_admin() will act on in isolation."""
    from app import models  # noqa: F401 — populate metadata for create_all

    path = Path(tempfile.mkdtemp()) / "bootstrap.db"
    eng = create_engine(f"sqlite:///{path.as_posix()}",
                        connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=eng, autoflush=False)
    db_module.Base.metadata.create_all(bind=eng)
    # _bootstrap_admin() closes over main.SessionLocal; point it here.
    monkeypatch.setattr(main, "SessionLocal", Session)
    yield Session
    eng.dispose()


def _set_production(monkeypatch, value: bool):
    from app.core.config import settings
    monkeypatch.setattr(type(settings), "is_production",
                        property(lambda self: value))


def _default_admin(Session):
    db = Session()
    try:
        return db.query(User).filter(User.email == "admin@eaios.dev").one_or_none()
    finally:
        db.close()


def test_production_does_not_create_a_known_password_admin(own_database, monkeypatch):
    _set_production(monkeypatch, True)
    main._bootstrap_admin()
    assert _default_admin(own_database) is None, \
        "production seeded admin@eaios.dev — its password is in the repo"


def test_development_still_gets_the_convenience_admin(own_database, monkeypatch):
    _set_production(monkeypatch, False)
    main._bootstrap_admin()
    admin = _default_admin(own_database)
    assert admin is not None and admin.role == "admin"
    assert verify_password("admin12345", admin.hashed_password), \
        "the dev convenience login stopped working"


def test_an_existing_default_admin_is_rotated_in_production(own_database, monkeypatch):
    """The account a previous build already created is closed on next boot."""
    _set_production(monkeypatch, False)
    main._bootstrap_admin()                       # simulate the vulnerable build
    assert verify_password("admin12345", _default_admin(own_database).hashed_password)

    _set_production(monkeypatch, True)
    main._bootstrap_admin()                       # deploying the fix

    admin = _default_admin(own_database)
    assert admin is not None, "rotation should disable the login, not delete the row"
    assert not verify_password("admin12345", admin.hashed_password), \
        "the shipped default password still works in production"


def test_rotation_is_idempotent(own_database, monkeypatch):
    """It runs on every boot; a second pass must not thrash the password."""
    _set_production(monkeypatch, False)
    main._bootstrap_admin()
    _set_production(monkeypatch, True)
    main._bootstrap_admin()
    first = _default_admin(own_database).hashed_password
    main._bootstrap_admin()
    second = _default_admin(own_database).hashed_password
    assert first == second, "rotation re-ran on an already-rotated account"
