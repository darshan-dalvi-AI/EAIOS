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

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    import shutil

    shutil.rmtree(_TMP, ignore_errors=True)
