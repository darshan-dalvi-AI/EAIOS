import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolated temp workspace — keeps test artifacts out of the repo and avoids
# SQLite locking issues on synced/network folders (OneDrive etc.).
_TMP = Path(tempfile.mkdtemp(prefix="eaios_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = (_TMP / "uploads").as_posix()
os.environ["LLM_PROVIDER"] = "mock"
os.environ["QDRANT_URL"] = ""
# Key derivation is deliberately expensive in production (600k rounds). The
# suite creates hundreds of accounts, so it uses a low cost — the strength of
# the KDF is not what these tests are checking.
os.environ["PASSWORD_HASH_ITERATIONS"] = "1000"
# Most tests exercise features, not onboarding, so they sign up and use the app
# immediately. Email verification is switched off here and switched ON explicitly
# by tests/test_email_verification.py, which is what actually checks the gate.
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "0"
# A (fake) key must exist for provider-switch tests: get_llm() only builds the
# OpenAI-compatible client when a key is present. LLM_PROVIDER=mock still wins.
os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"
# The suite performs 25+ real logins — disable rate limiting globally;
# test_ratelimit re-enables it per-test via monkeypatch.
os.environ["RATE_LIMIT_ENABLED"] = "0"
# Keep the background scheduler quiet during tests (run_due_scheduled is unit-tested directly).
os.environ["SCHEDULER_ENABLED"] = "0"
# Most tests exercise product behaviour, not commercial packaging, and the whole
# suite shares one workspace — so on the Free plan the fifth account created by
# any test would fail on a seat limit that test never meant to exercise.
# tests/test_industry_and_plans.py sets the plan it needs, per test.
os.environ["DEFAULT_PLAN"] = "business"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
