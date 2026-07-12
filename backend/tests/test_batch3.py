"""Batch-3 features: report exports, scheduled workflows, meeting minutes,
model arena, document analyzers."""
import io
import json

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient, email="admin@eaios.dev", pw="admin12345") -> dict:
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


MD = "# Quarterly Report\n\nRevenue grew strongly.\n\n## Highlights\n\n- Enterprise up 34%\n- Churn down\n\n```\nSELECT 1\n```\n"


# ── renderers ────────────────────────────────────────────────────────────
def test_pdf_renderer_produces_readable_pdf():
    from app.services.reports import build_pdf

    data = build_pdf("Quarterly Report", MD)
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")

    from pypdf import PdfReader

    text = "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    assert "Quarterly Report" in text
    assert "Enterprise up 34%" in text
    assert "EAIOS" in text  # footer


def test_docx_renderer_roundtrips():
    import docx

    from app.services.reports import build_docx

    data = build_docx("Quarterly Report", MD)
    d = docx.Document(io.BytesIO(data))
    all_text = "\n".join(p.text for p in d.paragraphs)
    assert "Quarterly Report" in all_text and "Enterprise up 34%" in all_text


def test_export_endpoint_pdf_and_docx():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/reports/export", headers=h, json={"title": "Board Pack", "content": MD, "format": "pdf"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert "board-pack.pdf" in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF")

        r = c.post("/api/reports/export", headers=h, json={"title": "Board Pack", "content": MD, "format": "docx"})
        assert r.status_code == 200
        assert r.content[:2] == b"PK"  # zip container


# ── scheduled workflows ──────────────────────────────────────────────────
def test_scheduler_fires_due_workflows_once_per_interval():
    with client() as c:
        h = _headers(c)
        r = c.post("/api/workflows", headers=h, json={
            "name": "hourly-digest", "trigger": "schedule", "enabled": True,
            "nodes": [{"id": "t", "type": "trigger", "x": 0, "y": 0, "data": {"every": 1}},
                      {"id": "n", "type": "notify", "x": 1, "y": 0, "data": {"message": "digest: {{input}}"}}],
            "edges": [{"from": "t", "to": "n"}],
        })
        assert r.status_code in (200, 201), r.text

        from app.core.database import SessionLocal
        from app.services.workflows import run_due_scheduled

        with SessionLocal() as db:
            assert run_due_scheduled(db) >= 1      # never ran → due now
        with SessionLocal() as db:
            assert run_due_scheduled(db) == 0      # 1-minute interval not yet elapsed

        runs = c.get(f"/api/workflows/{r.json()['id']}/runs", headers=h).json()
        assert runs and runs[0]["trigger"] == "schedule"


# ── meeting assistant ────────────────────────────────────────────────────
def test_meeting_minutes_and_save_to_knowledge():
    transcript = (
        "Maya: We decided to go with OpenRouter for the model layer. "
        "Rohan will send the cost report by Friday. "
        "Team agreed the launch is approved for next sprint. "
        "Darshan will prepare the demo environment and follow up with QA."
    )
    with client() as c:
        h = _headers(c)
        r = c.post("/api/agents/meeting", headers=h,
                   json={"transcript": transcript, "title": "Sprint Sync", "save_to_knowledge": True})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "## Summary" in body["minutes"]
        assert "## Decisions" in body["minutes"]
        assert "## Action Items" in body["minutes"]
        assert body["doc_id"]

        # background ingest ran (TestClient waits) → document indexed & searchable
        docs = c.get("/api/documents", headers=h).json()
        mine = next(d for d in docs if d["id"] == body["doc_id"])
        assert mine["status"] == "indexed" and mine["chunk_count"] >= 1


# ── model arena ──────────────────────────────────────────────────────────
def test_compare_is_admin_only_and_returns_two_results():
    with client() as c:
        admin = _headers(c)
        c.post("/api/auth/register",
               json={"email": "arena@test.dev", "full_name": "Arena Tester", "password": "password123"})
        emp = _headers(c, "arena@test.dev", "password123")

        r = c.post("/api/admin/compare", headers=emp,
                   json={"prompt": "What is EAIOS?", "models": ["a/x", "b/y"]})
        assert r.status_code == 403

        r = c.post("/api/admin/compare", headers=admin,
                   json={"prompt": "What is EAIOS?", "models": ["openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"]})
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) == 2
        # mock provider → deterministic per-model variants, no errors
        assert all(x["error"] is None and x["answer"].startswith(f"[{x['model']}]") for x in results)
        assert all(isinstance(x["ms"], int) for x in results)


# ── document analyzers ───────────────────────────────────────────────────
def _upload(c, h, name: str, text: str) -> str:
    r = c.post("/api/documents/upload", headers=h, files={"file": (name, text.encode(), "text/plain")})
    assert r.status_code == 201
    return r.json()["id"]


def test_analyzer_resume_and_contract_scorecards():
    with client() as c:
        h = _headers(c)
        resume_id = _upload(c, h, "jane_resume.txt",
                            "Jane Doe — Senior Engineer. Skills: Python, React, SQL, Docker, AWS. "
                            "Built FastAPI services. Contact: jane@example.com. 6 years experience.")
        contract_id = _upload(c, h, "vendor_contract.txt",
                              "Master Services Agreement. Termination requires 90 days notice. "
                              "Liability is capped at $50,000. Confidentiality survives termination. "
                              "Payment due within 30 days. Signed March 3, 2026.")

        r = c.post(f"/api/documents/{resume_id}/analyze", headers=h, json={"kind": "resume"})
        assert r.status_code == 200, r.text
        card = r.json()
        assert card["kind"] == "resume" and 0 <= card["score"] <= 100
        assert any("python" in hl["value"].lower() for hl in card["highlights"])

        r = c.post(f"/api/documents/{contract_id}/analyze", headers=h, json={"kind": "contract"})
        card = r.json()
        assert card["kind"] == "contract"
        joined = json.dumps(card["highlights"]).lower()
        assert "termination" in joined or "liability" in joined

        # invalid kind rejected by validation
        r = c.post(f"/api/documents/{resume_id}/analyze", headers=h, json={"kind": "horoscope"})
        assert r.status_code == 422
