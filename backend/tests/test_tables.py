"""Advanced document parsing: structured tables → REAL SQL tables → SQL Agent."""
from fastapi.testclient import TestClient
from sqlalchemy import text as sqltext

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _headers(c: TestClient) -> dict:
    r = c.post("/api/auth/login", json={"email": "admin@eaios.dev", "password": "admin12345"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']['access_token']}"}


# ── unit: text-grid detection ────────────────────────────────────────────
def test_detect_text_tables_markdown_and_space_grid():
    from app.rag.tables import detect_text_tables

    md = (
        "Quarterly revenue report — intro prose that is not a table.\n\n"
        "| region | q1 | q2 |\n"
        "|--------|----|----|\n"
        "| North  | 120 | 140 |\n"
        "| South  | 95  | 90  |\n"
        "| West   | 60  | 75  |\n\n"
        "Closing prose line."
    )
    tables = detect_text_tables(md)
    assert len(tables) == 1
    assert tables[0].columns == ["region", "q1", "q2"]
    assert len(tables[0].rows) == 3

    grid = (
        "Name        Dept        Salary\n"
        "Maya        Finance     90000\n"
        "Rohan       Sales       72000\n"
        "Asha        HR          65000\n"
    )
    tables = detect_text_tables(grid)
    assert len(tables) == 1
    assert tables[0].columns == ["Name", "Dept", "Salary"]
    assert len(tables[0].rows) == 3

    # prose alone must NOT look like a table
    assert detect_text_tables("Just a sentence.\nAnd another one here.\nNothing tabular.") == []


def test_type_inference_and_identifier_hygiene():
    from app.rag.tables import infer_types, sanitize_ident

    rows = [["North", "120", "1.5"], ["South", "95", "2.25"], ["West", "60", "3.0"]]
    assert infer_types(rows, 3) == ["TEXT", "INTEGER", "REAL"]

    used: set[str] = set()
    assert sanitize_ident("Q1 Revenue ($M)", used, "col_1") == "q1_revenue_m"
    assert sanitize_ident("Q1 Revenue ($M)", used, "col_2") == "q1_revenue_m_2"  # dedupe
    assert sanitize_ident("123", used, "col_3") == "col_3"  # must start with letter


# ── end-to-end: upload → materialize → query via SQL Agent ───────────────
def test_csv_upload_materializes_queryable_sql_table():
    csv_bytes = b"region,q1_revenue,q2_revenue\nNorth,120,140\nSouth,95,90\nWest,60,75\n"
    with client() as c:
        h = _headers(c)
        r = c.post("/api/documents/upload", headers=h,
                   files={"file": ("regional_sales.csv", csv_bytes, "text/csv")})
        assert r.status_code == 201
        doc_id = r.json()["id"]

        # background ingest ran → document indexed with a table
        from app.core.database import SessionLocal
        from app.models import DataTable

        with SessionLocal() as db:
            dts = db.query(DataTable).filter(DataTable.document_id == doc_id).all()
            assert len(dts) == 1
            dt = dts[0]
            assert dt.table_name.startswith("dt_")
            assert dt.row_count == 3
            rows = db.execute(sqltext(f'SELECT SUM(q1_revenue) FROM "{dt.table_name}"')).scalar()
            assert rows == 275  # structured data survived intact
            table_name = dt.table_name

        # summary chunk indexed for RAG citation
        chunks = c.get(f"/api/documents/{doc_id}/chunks", headers=h).json()
        assert any("STRUCTURED TABLE" in ch["text"] for ch in chunks)

        # schema explorer lists the extracted table with provenance
        schema = c.get("/api/agents/sql/schema", headers=h).json()
        entry = next((t for t in schema if t["table"] == table_name), None)
        assert entry is not None and "Regional Sales" in entry["source"]

        # SQL Agent heuristic targets the uploaded table by document title
        r = c.post("/api/agents/sql", headers=h,
                   json={"question": "Show me the regional sales table"})
        assert r.status_code == 200
        body = r.json()
        assert table_name in body["sql"]
        assert len(body["rows"]) == 3

        # reindex is idempotent: still exactly one DataTable, fresh physical rows
        assert c.post(f"/api/documents/{doc_id}/reindex", headers=h).status_code == 200
        with SessionLocal() as db:
            assert db.query(DataTable).filter(DataTable.document_id == doc_id).count() == 1
            assert db.execute(sqltext(f'SELECT COUNT(*) FROM "{table_name}"')).scalar() == 3

        # delete drops metadata AND the physical table
        assert c.delete(f"/api/documents/{doc_id}", headers=h).status_code == 204
        with SessionLocal() as db:
            assert db.query(DataTable).filter(DataTable.document_id == doc_id).count() == 0
            try:
                db.execute(sqltext(f'SELECT COUNT(*) FROM "{table_name}"'))
                raise AssertionError("physical table should be gone")
            except AssertionError:
                raise
            except Exception:
                pass  # expected: no such table


def test_schema_description_includes_data_tables():
    from app.agents.sql_agent import schema_description
    from app.core.database import SessionLocal, init_db
    from app.models import DataTable

    init_db()
    with SessionLocal() as db:
        db.add(DataTable(document_id="docx1", doc_title="Budget 2026", table_name="dt_test_schema_1",
                         title="Sheet1", columns='[{"name": "dept", "type": "TEXT"}]', row_count=4))
        db.commit()
        desc = schema_description(db)
        assert "dt_test_schema_1(dept TEXT)" in desc
        assert "Budget 2026" in desc
        db.execute(sqltext("DELETE FROM data_tables WHERE table_name = 'dt_test_schema_1'"))
        db.commit()
