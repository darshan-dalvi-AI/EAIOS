"""EAIOS backend — FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin, agents, analytics, auth, chat, connectors, dashboards, documents,
    graph, me, reports, search, studio, tasks, traces, users, workflows, ws,
)
from app.core.config import settings
from app.core.database import SessionLocal, init_db

log = logging.getLogger("eaios")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _bootstrap_admin() -> None:
    """Create a first admin if the user table is empty, so a fresh clone is usable immediately."""
    from app.core.security import hash_password
    from app.models import User

    with SessionLocal() as db:
        if db.query(User).count() == 0:
            db.add(User(
                email="admin@eaios.dev",
                full_name="System Administrator",
                hashed_password=hash_password("admin12345"),
                role="admin",
                avatar_hue=265,
            ))
            db.commit()
            log.info("Bootstrapped admin → admin@eaios.dev / admin12345 (change this!)")


def _seed_if_empty() -> None:
    """SEED_ON_START=1 (single-container/cloud mode): populate demo users +
    documents on an empty database so a fresh deploy is instantly demoable.
    Idempotent — seed() skips anything that already exists."""
    import os

    if os.environ.get("SEED_ON_START") != "1":
        return
    from app.models import Document

    with SessionLocal() as db:
        if db.query(Document).count() > 0:
            return
    try:
        from app.seed import seed

        seed()
        log.info("Seeded demo corpus (SEED_ON_START=1)")
    except Exception:  # noqa: BLE001 — a failed seed must not block boot
        log.exception("SEED_ON_START failed; continuing with empty KB")


async def _schedule_loop() -> None:
    """Fire due `trigger=schedule` workflows every SCHEDULER_INTERVAL seconds.
    Workflow execution is sync/blocking, so each tick runs in a worker thread."""
    from app.services import workflows as wf_service

    def tick() -> int:
        with SessionLocal() as db:
            fired = wf_service.run_due_scheduled(db)
            # Data retention (compliance): purge conversations older than RETENTION_DAYS
            if settings.RETENTION_DAYS > 0:
                from datetime import datetime, timedelta, timezone

                from sqlalchemy import delete as sqldelete, select

                from app.models import Conversation, Message

                cutoff = datetime.now(timezone.utc) - timedelta(days=settings.RETENTION_DAYS)
                old_ids = [c.id for c in db.scalars(select(Conversation).where(Conversation.updated_at < cutoff)).all()]
                if old_ids:
                    db.execute(sqldelete(Message).where(Message.conversation_id.in_(old_ids)))
                    db.execute(sqldelete(Conversation).where(Conversation.id.in_(old_ids)))
                    db.commit()
                    log.info("retention: purged %d conversation(s) older than %dd", len(old_ids), settings.RETENTION_DAYS)
            return fired

    while True:
        await asyncio.sleep(settings.SCHEDULER_INTERVAL)
        try:
            fired = await asyncio.to_thread(tick)
            if fired:
                log.info("scheduler: fired %d workflow(s)", fired)
        except Exception:  # noqa: BLE001 — the scheduler must never die
            log.exception("scheduler tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _bootstrap_admin()
    _seed_if_empty()
    from app.core import storage

    storage.ensure_bucket()  # create the Supabase Storage bucket if configured (idempotent)
    task = asyncio.create_task(_schedule_loop()) if settings.SCHEDULER_ENABLED else None
    log.info("EAIOS %s ready — llm=%s scheduler=%s", settings.VERSION, settings.LLM_PROVIDER,
             "on" if task else "off")
    yield
    if task:
        task.cancel()


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

# Rate limiting first, CORS last → CORS is outermost, so even 429s carry CORS headers.
from app.core.ratelimit import RateLimitMiddleware  # noqa: E402

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router, users.router, documents.router, chat.router, agents.router,
    admin.router, analytics.router, graph.router, workflows.router, traces.router,
    reports.router, dashboards.router, studio.router, connectors.router,
    tasks.router, search.router, me.router, ws.router,
):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    from app.llm.provider import get_llm

    llm = get_llm()
    return {
        "status": "ok",
        "version": settings.VERSION,
        "llm_provider": llm.name,
        "llm_model": getattr(llm, "model", None),
    }


# ── single-container mode (Dockerfile.web / Render / HF Spaces) ──────────
# If a built frontend sits next to the app, serve it from the same process:
# one URL for UI + API + WebSocket, zero CORS. API routes above win; this
# mount only catches what they don't.
import os as _os  # noqa: E402

_static_dir = _os.environ.get(
    "FRONTEND_DIST",
    _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", "static")),
)
if _os.path.isdir(_static_dir):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="spa")
    log.info("Single-container mode: serving frontend from %s", _static_dir)
