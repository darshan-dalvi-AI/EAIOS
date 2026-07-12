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
# A (fake) key must exist for provider-switch tests: get_llm() only builds the
# OpenAI-compatible client when a key is present. LLM_PROVIDER=mock still wins.
os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"
# The suite performs 25+ real logins — disable rate limiting globally;
# test_ratelimit re-enables it per-test via monkeypatch.
os.environ["RATE_LIMIT_ENABLED"] = "0"
# Keep the background scheduler quiet during tests (run_due_scheduled is unit-tested directly).
os.environ["SCHEDULER_ENABLED"] = "0"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
