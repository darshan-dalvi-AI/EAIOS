"""Blob storage abstraction — local disk in dev, Supabase Storage in prod.

Dev/demo: uploaded files live on local disk under ``UPLOAD_DIR`` (zero config).
Production: when ``SUPABASE_URL`` + ``SUPABASE_SERVICE_KEY`` are set, every file
is ALSO mirrored to a Supabase Storage bucket, so documents survive a container
redeploy exactly like the database now does. ``ensure_local`` transparently
re-downloads a file from Supabase when the local cache is cold (fresh container
after a deploy). All remote calls fail soft — a storage hiccup never breaks an
upload; the local copy always works within the current container's lifetime.
"""
from __future__ import annotations

import logging
import os

import httpx

from app.core.config import settings

log = logging.getLogger("eaios.storage")


def enabled() -> bool:
    """Read live so tests/config changes are picked up without a reload."""
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _local(key: str) -> str:
    return os.path.join(settings.UPLOAD_DIR, key)


def _object_url(key: str) -> str:
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/storage/v1/object/{settings.STORAGE_BUCKET}/{key}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_KEY,
    }


def ensure_bucket() -> None:
    """Create the storage bucket (idempotent) AND enforce that it is private —
    called on app startup.

    Creating with ``public: False`` only helps the first time. If the bucket
    already exists — perhaps created public in the dashboard before this code, or
    by an older build — the create call just errors and the bucket keeps whatever
    visibility it had. So we also PUT ``public: False`` every boot: the code, not
    a dashboard toggle, is the source of truth, and a bucket can never silently
    drift to public. Uploaded files are fetched with the service key
    (``ensure_local``), never a public URL, so private is the correct setting.
    """
    if not enabled():
        return
    base = settings.SUPABASE_URL.rstrip("/")
    headers = {**_headers(), "Content-Type": "application/json"}
    body = {"id": settings.STORAGE_BUCKET, "name": settings.STORAGE_BUCKET, "public": False}
    try:
        httpx.post(f"{base}/storage/v1/bucket", headers=headers, json=body,
                   timeout=15, trust_env=False)
    except Exception:  # noqa: BLE001 — bucket likely already exists; never block boot
        pass
    # Enforce private even if the bucket pre-existed (create above is a no-op then).
    try:
        r = httpx.put(f"{base}/storage/v1/bucket/{settings.STORAGE_BUCKET}",
                      headers=headers, json={"public": False}, timeout=15, trust_env=False)
        if r.status_code < 300:
            log.info("Supabase Storage bucket '%s' ready and private", settings.STORAGE_BUCKET)
        else:
            log.warning("Could not enforce private bucket (%s): %s",
                        settings.STORAGE_BUCKET, r.status_code)
    except Exception:  # noqa: BLE001 — never block boot
        pass


def put(key: str, src_path: str) -> None:
    """Mirror an already-written local file to Supabase Storage. No-op when
    storage is disabled; failures are logged but swallowed."""
    if not enabled():
        return
    try:
        with open(src_path, "rb") as f:
            data = f.read()
        httpx.post(
            _object_url(key),
            headers={**_headers(), "x-upsert": "true", "Content-Type": "application/octet-stream"},
            content=data,
            timeout=45, trust_env=False,
        )
    except Exception:  # noqa: BLE001 — local copy still serves this container
        log.warning("Supabase Storage upload failed for %s", key, exc_info=True)


def ensure_local(key: str) -> str | None:
    """Return a local filesystem path for ``key``, downloading it from Supabase
    Storage first if the local cache is cold. Returns ``None`` if the file
    exists in neither place (e.g. storage disabled and cache wiped)."""
    path = _local(key)
    if os.path.exists(path):
        return path
    if enabled():
        try:
            r = httpx.get(_object_url(key), headers=_headers(), timeout=45, trust_env=False)
            if r.status_code == 200 and r.content:
                os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(r.content)
                return path
        except Exception:  # noqa: BLE001
            log.warning("Supabase Storage fetch failed for %s", key, exc_info=True)
    return None


def remove(key: str) -> None:
    """Delete a file locally and (if enabled) from Supabase Storage."""
    try:
        os.remove(_local(key))
    except OSError:
        pass
    if enabled():
        try:
            httpx.request("DELETE", _object_url(key), headers=_headers(), timeout=15, trust_env=False)
        except Exception:  # noqa: BLE001
            pass
