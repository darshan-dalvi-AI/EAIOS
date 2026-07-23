"""Blob storage layer: local-disk default + Supabase mirror behavior.

`enabled()` reads settings live, so tests just monkeypatch the settings object —
no module reloads (which would pollute global state for the rest of the suite).
The remote path runs against a tiny in-process fake Supabase Storage server."""
import http.server
import os
import threading

from app.core import storage
from app.core.config import settings


def test_local_mode_is_transparent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")

    assert storage.enabled() is False
    # the upload handler writes the file at the key path, then calls put()
    f = tmp_path / "abc.txt"
    f.write_text("hello")
    storage.put("abc.txt", str(f))            # remote no-op in local mode
    assert storage.ensure_local("abc.txt")    # local file present
    assert storage.ensure_local("missing.txt") is None


def test_supabase_mirror_roundtrip(tmp_path, monkeypatch):
    store: dict[str, bytes] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def _key(self):
            return self.path.split("/documents/")[-1]

        def do_POST(self):
            if "/bucket" in self.path:
                self.send_response(200); self.end_headers(); return
            n = int(self.headers.get("Content-Length", 0))
            store[self._key()] = self.rfile.read(n)
            self.send_response(200); self.end_headers()

        def do_GET(self):
            data = store.get(self._key())
            if data is None:
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
            self.wfile.write(data)

        def do_DELETE(self):
            store.pop(self._key(), None)
            self.send_response(200); self.end_headers()

        def log_message(self, *a):  # silence
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(settings, "SUPABASE_URL", base)
        monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "test-service-key")
        monkeypatch.setattr(settings, "STORAGE_BUCKET", "documents")

        assert storage.enabled() is True
        storage.ensure_bucket()

        f = tmp_path / "doc1.txt"          # == _local("doc1.txt")
        f.write_text("enterprise data")
        storage.put("doc1.txt", str(f))
        assert store.get("doc1.txt") == b"enterprise data"       # mirrored to "Supabase"

        # simulate a fresh container: wipe local cache → ensure_local re-fetches
        os.remove(f)
        got = storage.ensure_local("doc1.txt")
        assert got and open(got, "rb").read() == b"enterprise data"

        storage.remove("doc1.txt")
        assert "doc1.txt" not in store
    finally:
        srv.shutdown()
