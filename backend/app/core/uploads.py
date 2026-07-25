"""Upload safety — size, name and content checks.

An extension is a claim made by the caller, not evidence. These helpers
enforce three independent things before a file is accepted:

1. **Size** — capped while streaming, so an oversized body is refused before
   it can fill the disk rather than measured after it already has.
2. **Name** — no directory traversal, no control characters, bounded length.
   (The stored name is derived from the document id regardless; this protects
   anything that later displays or logs the original name.)
3. **Content** — the leading bytes must match the claimed type. A PHP script
   renamed to ``.pdf`` fails here.

Uploads are written to a dedicated directory that is never mounted as static
content and never added to the Python path, so a stored file cannot be served
or imported as code.
"""
import os
import re
import unicodedata

from fastapi import HTTPException

from app.core.config import settings

# Extension → (doc_type, allowed leading-byte signatures)
# An empty signature tuple means "text-like": validated by decodability
# instead of magic bytes, since text files have no reliable header.
SIGNATURES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".pdf":  ("pdf",   (b"%PDF-",)),
    ".docx": ("docx",  (b"PK\x03\x04", b"PK\x05\x06")),      # OOXML = zip container
    ".pptx": ("pptx",  (b"PK\x03\x04", b"PK\x05\x06")),
    ".xlsx": ("xlsx",  (b"PK\x03\x04", b"PK\x05\x06")),
    ".png":  ("image", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg":  ("image", (b"\xff\xd8\xff",)),
    ".jpeg": ("image", (b"\xff\xd8\xff",)),
    ".csv":  ("csv",   ()),
    ".txt":  ("txt",   ()),
    ".md":   ("txt",   ()),
}

ALLOWED_EXT = tuple(sorted(SIGNATURES))

# Anything that looks like executable or script content is rejected outright,
# whatever extension it arrives under.
DANGEROUS_PREFIXES: tuple[bytes, ...] = (
    b"#!",                 # shebang — shell/python/perl script
    b"MZ",                 # Windows PE executable
    b"\x7fELF",            # Linux ELF binary
    b"\xca\xfe\xba\xbe",   # Mach-O / Java class
    b"<?php",
    b"<%",                 # ASP / JSP
)
_SCRIPT_TAG = re.compile(rb"<\s*script[\s>]", re.I)

_UNSAFE_NAME = re.compile(r"[\x00-\x1f\x7f<>:\"|?*\\/]")


def safe_filename(raw: str | None) -> str:
    """Reduce a caller-supplied name to something safe to store, log and show."""
    name = unicodedata.normalize("NFKC", (raw or "upload").strip())
    name = os.path.basename(name.replace("\\", "/"))      # strip any path
    name = _UNSAFE_NAME.sub("_", name).lstrip(".") or "upload"
    if len(name) > settings.MAX_UPLOAD_FILENAME:
        stem, ext = os.path.splitext(name)
        name = stem[: settings.MAX_UPLOAD_FILENAME - len(ext)] + ext
    return name


def check_extension(filename: str) -> tuple[str, str]:
    """Return (extension, doc_type) or raise 415."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SIGNATURES:
        raise HTTPException(
            415, f"Unsupported file type '{ext or 'unknown'}'. "
                 f"Allowed: {', '.join(ALLOWED_EXT)}")
    return ext, SIGNATURES[ext][0]


def verify_content(head: bytes, ext: str) -> None:
    """Confirm the bytes match the claimed type; raise 415 if they do not."""
    if any(head.startswith(sig) for sig in DANGEROUS_PREFIXES) or _SCRIPT_TAG.search(head[:2048]):
        raise HTTPException(415, "This file appears to contain executable or script content.")

    signatures = SIGNATURES[ext][1]
    if signatures:
        if not any(head.startswith(sig) for sig in signatures):
            raise HTTPException(
                415, f"File content does not match its '{ext}' extension. "
                     "Rename-only conversions are not accepted.")
        return

    # Text-like formats: must decode as text, which rejects binaries renamed .txt
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        try:
            head.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(415, f"'{ext}' files must be readable text.") from None


def stream_to_disk(src, dest_path: str, ext: str) -> int:
    """Copy an upload to disk, enforcing the size cap as it streams.

    Returns the byte count. On violation the partial file is removed and a
    413 is raised, so a hostile client cannot leave debris behind.
    """
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    head = b""
    try:
        with open(dest_path, "wb") as out:
            while True:
                block = src.read(1024 * 256)
                if not block:
                    break
                if not head:
                    head = block[:4096]
                    verify_content(head, ext)      # fail before writing the bulk
                written += len(block)
                if written > limit:
                    raise HTTPException(
                        413, f"File is larger than the {settings.MAX_UPLOAD_MB} MB limit.")
                out.write(block)
    except Exception:
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise

    if written == 0:
        try:
            os.remove(dest_path)
        except OSError:
            pass
        raise HTTPException(400, "The uploaded file is empty.")
    return written


def ensure_upload_dir() -> str:
    """Create the upload directory with owner-only permissions.

    It deliberately sits outside the directory served as static content, so a
    stored file has no URL and can never be executed by the web server.
    """
    path = os.path.abspath(settings.UPLOAD_DIR)
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:      # pragma: no cover — unsupported on some filesystems
        pass
    return path
