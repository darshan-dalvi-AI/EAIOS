"""Connectors — pull items from external sources into the RAG pipeline.

Each provider returns a list of ``(title, doc_type, text)`` items; the sync
step materializes them as Document rows and runs them through the same
ingestion pipeline as uploaded files, so connected data becomes searchable,
citable, entity-linked and (for tables) query-able exactly like uploads.

Providers:
  · sample        — a bundled demo "workspace" (Gmail threads + Drive docs);
                    always works, zero credentials, great for demos/tests.
  · google_drive  — real Google Drive via a user-supplied OAuth access token
                    (Drive API v3: list files, export Google Docs as text).
  · gmail         — real Gmail via an OAuth access token (Gmail API: recent
                    message snippets).
The OAuth *consent* flow (obtaining the token) is documented in docs/DEPLOY.md;
once you have a token the providers below fetch and ingest real data.
"""
import logging
import os

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Connector, Document

log = logging.getLogger("eaios.connectors")

PROVIDERS = ("sample", "google_drive", "gmail")

# ── bundled demo workspace ───────────────────────────────────────────────
_SAMPLE_ITEMS = [
    ("Gmail — Q3 board deck review", "txt",
     "From: cfo@acme.example\nTo: exec@acme.example\nSubject: Q3 board deck review\n\n"
     "Team, the Q3 numbers are locked: revenue $54.2M (+18% YoY), gross margin 71%, net retention 122%. "
     "Enterprise segment led growth; SMB churn ticked up 1.4pts. Action: Priya to finalize the board deck by Friday, "
     "Rohan to prep the retention deep-dive. We present to the board on the 14th."),
    ("Gmail — Security review: Nimbus contract", "txt",
     "From: ciso@acme.example\nTo: legal@acme.example\nSubject: Security review — Nimbus Cloud MSA\n\n"
     "Completed the security review of the Nimbus Cloud master services agreement. Liability is capped at $250k, "
     "which is low for a contract of this size. Data processing addendum is GDPR-compliant. Recommend we negotiate "
     "the cap up before signing. Contact for escalations: neha.rao@acme.example or +1 (415) 555-0137."),
    ("Drive — HR Leave Policy 2026", "txt",
     "# HR Leave Policy 2026\n\n## Annual leave\nEmployees receive 24 days of paid annual leave per year, credited monthly. "
     "Up to 10 unused days may be carried forward into the next year; anything beyond that is forfeited.\n\n"
     "## Work from home\nEmployees may work remotely up to 3 days per week with manager approval.\n\n"
     "## Sick leave\n12 days of paid sick leave annually, no carry-forward."),
    ("Drive — Regional sales (structured)", "csv",
     "region,q1_revenue,q2_revenue,q3_revenue\nNorth,120,140,165\nSouth,95,90,105\nWest,60,75,88\nEast,150,160,172"),
    ("Drive — Engineering onboarding runbook", "txt",
     "# Engineering Onboarding\n\nDay 1: accounts, laptop, repo access. Day 2: architecture walkthrough — "
     "React OS shell → FastAPI → graph orchestrator → hybrid RAG → pluggable LLMs. Day 3: ship a small PR. "
     "Stack: React 18, TypeScript, FastAPI, SQLAlchemy, Qdrant, OpenRouter. Ask #eng-help for anything."),
]


def _fetch_sample() -> list[tuple[str, str, str]]:
    return list(_SAMPLE_ITEMS)


def _fetch_google_drive(token: str, limit: int = 15) -> list[tuple[str, str, str]]:
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        params={"pageSize": limit, "fields": "files(id,name,mimeType)",
                "q": "trashed=false and (mimeType='application/vnd.google-apps.document' "
                     "or mimeType='text/plain' or mimeType='text/csv')"},
        timeout=20,
    )
    r.raise_for_status()
    items: list[tuple[str, str, str]] = []
    for f in r.json().get("files", []):
        try:
            if f["mimeType"] == "application/vnd.google-apps.document":
                exp = httpx.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}/export",
                                headers=headers, params={"mimeType": "text/plain"}, timeout=20)
                exp.raise_for_status()
                text = exp.text
            else:
                dl = httpx.get(f"https://www.googleapis.com/drive/v3/files/{f['id']}",
                               headers=headers, params={"alt": "media"}, timeout=20)
                dl.raise_for_status()
                text = dl.text
            dtype = "csv" if f["name"].lower().endswith(".csv") or f["mimeType"] == "text/csv" else "txt"
            if text.strip():
                items.append((f"Drive — {f['name']}", dtype, text[:200_000]))
        except Exception:  # noqa: BLE001 — skip a file we can't read
            log.exception("drive export failed for %s", f.get("name"))
    return items


def _fetch_gmail(token: str, limit: int = 15) -> list[tuple[str, str, str]]:
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    lst = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    headers=headers, params={"maxResults": limit, "q": "in:inbox"}, timeout=20)
    lst.raise_for_status()
    items: list[tuple[str, str, str]] = []
    for m in lst.json().get("messages", []):
        try:
            msg = httpx.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                            headers=headers, params={"format": "metadata",
                                                     "metadataHeaders": ["Subject", "From"]}, timeout=20).json()
            hdrs = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subj = hdrs.get("Subject", "(no subject)")
            snippet = msg.get("snippet", "")
            items.append((f"Gmail — {subj}", "txt", f"From: {hdrs.get('From', '')}\nSubject: {subj}\n\n{snippet}"))
        except Exception:  # noqa: BLE001
            log.exception("gmail fetch failed for %s", m.get("id"))
    return items


_BLOCKED_HOSTS = ("localhost", "127.", "0.0.0.0", "10.", "192.168.", "169.254.", "172.16.", "172.17.", "[::1]", "metadata")


def _strip_html(html: str) -> str:
    import re
    html = re.sub(r"(?is)<(script|style|nav|footer|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    import html as h
    return re.sub(r"\s{2,}", " ", h.unescape(html)).strip()


def _fetch_website(url: str, max_pages: int = 8) -> list[tuple[str, str, str]]:
    """Crawl a site breadth-first (same host only) and return page texts."""
    import re
    from urllib.parse import urljoin, urlparse

    import httpx

    start = urlparse(url if "://" in url else f"https://{url}")
    if start.scheme not in ("http", "https") or not start.netloc:
        raise ValueError("Enter a full website URL, e.g. https://docs.example.com")
    if any(start.netloc.lower().startswith(b) or b in start.netloc.lower() for b in _BLOCKED_HOSTS):
        raise ValueError("That host isn't allowed.")

    seen: set[str] = set()
    queue = [start.geturl()]
    items: list[tuple[str, str, str]] = []
    with httpx.Client(follow_redirects=True, timeout=8, headers={"User-Agent": "EAIOS-connector/1.0"}) as client:
        while queue and len(items) < max_pages:
            page = queue.pop(0)
            if page in seen:
                continue
            seen.add(page)
            try:
                r = client.get(page)
                if r.status_code != 200 or "text/html" not in r.headers.get("content-type", "text/html"):
                    continue
                html = r.text[:400_000]
            except Exception:  # noqa: BLE001
                continue
            m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
            title = _strip_html(m.group(1))[:150] if m else page
            text = _strip_html(html)[:20_000]
            if len(text) > 80:
                items.append((f"Web — {title}", "txt", f"Source: {page}\n\n{text}"))
            for href in re.findall(r'(?i)href="([^"#?]+)"', html)[:60]:
                nxt = urljoin(page, href)
                p = urlparse(nxt)
                if p.netloc == start.netloc and p.scheme in ("http", "https") and nxt not in seen:
                    queue.append(nxt)
    if not items:
        raise ValueError("Couldn't read any pages from that URL — check it's reachable and returns HTML.")
    return items


def fetch(provider: str, token: str = "") -> list[tuple[str, str, str]]:
    if provider == "sample":
        return _fetch_sample()
    if provider == "google_drive":
        if not token:
            raise ValueError("Google Drive needs an OAuth access token (paste one, or set up the consent flow).")
        return _fetch_google_drive(token)
    if provider == "gmail":
        if not token:
            raise ValueError("Gmail needs an OAuth access token.")
        return _fetch_gmail(token)
    if provider == "website":
        if not token:
            raise ValueError("Website connector needs a URL.")
        return _fetch_website(token)
    raise ValueError(f"Unknown provider '{provider}'")


def sync(db: Session, connector: Connector, token: str = "") -> int:
    """Fetch items from the provider and ingest each into the RAG pipeline.
    Returns the number of documents ingested."""
    from app.rag import pipeline

    items = fetch(connector.provider, token)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ingested = 0
    for title, dtype, text in items:
        doc = Document(
            filename=f"connector_{connector.provider}_{ingested}.{dtype}",
            title=title[:255], doc_type=dtype, owner_id=connector.owner_id, status="queued",
            tags=f"connector,{connector.provider}",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        dest = os.path.join(settings.UPLOAD_DIR, f"{doc.id}.{dtype}")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
        doc.size_bytes = os.path.getsize(dest)
        db.commit()
        pipeline.ingest_document(doc.id, dest)  # synchronous so the count is accurate
        ingested += 1
    return ingested
