"""EAIOS backend — FastAPI application entry point."""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import (
    admin, agents, analytics, auth, chat, connectors, dashboards, documents,
    graph, me, orgs, reports, search, studio, tasks, traces, users, workflows, ws,
)
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.services.plans import LimitReached

log = logging.getLogger("eaios")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


_BOOTSTRAP_EMAIL = "admin@eaios.dev"
_BOOTSTRAP_DEV_PASSWORD = "admin12345"  # dev convenience ONLY — never in production


def _bootstrap_admin() -> None:
    """Make a fresh clone usable — WITHOUT shipping a login anyone can use.

    The convenience of a known admin/admin password is fine on a developer's
    laptop and a disaster on a public URL: the password is in this repository,
    so anyone who reads it can sign in as admin. So:

      * In production the known-password admin is never created. The first real
        user arrives through signup (which makes them their workspace's admin)
        or through PLATFORM_OWNER_EMAILS.
      * If a previous build already created that account with the shipped
        password, this rotates it to a random value on every boot — so simply
        deploying this change closes the hole on an existing database.
      * On a non-production machine the old convenience is unchanged.
    """
    import secrets

    from app.core.security import hash_password, verify_password
    from app.models import User

    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == _BOOTSTRAP_EMAIL).one_or_none()

        # Close an account a prior build left with the source-controlled password.
        # Runs every boot; only fires while the default still works, so it is a
        # no-op once rotated.
        if (existing is not None and settings.is_production
                and verify_password(_BOOTSTRAP_DEV_PASSWORD, existing.hashed_password)):
            existing.hashed_password = hash_password(secrets.token_urlsafe(24))
            db.commit()
            log.warning(
                "Rotated %s off the shipped default password. Sign in via signup "
                "or PLATFORM_OWNER_EMAILS; that account is now inaccessible.",
                _BOOTSTRAP_EMAIL)
            return

        if existing is not None or db.query(User).count() > 0:
            return  # already initialised — nothing to bootstrap

        if settings.is_production:
            # A public deployment must not seed a password that lives in git.
            log.warning(
                "Empty user table in production — not seeding a default admin. "
                "Create your workspace via signup, or set PLATFORM_OWNER_EMAILS.")
            return

        from app.services.tenancy import default_org

        db.add(User(
            email=_BOOTSTRAP_EMAIL,
            full_name="System Administrator",
            hashed_password=hash_password(_BOOTSTRAP_DEV_PASSWORD),
            role="admin",
            avatar_hue=265,
            org_id=default_org(db).id,
            # Created by the platform, not by a signup — there is no address to
            # prove, and gating it would lock the local demo out.
            email_verified=True,
        ))
        db.commit()
        log.info("Bootstrapped dev admin → %s / %s (development only)",
                 _BOOTSTRAP_EMAIL, _BOOTSTRAP_DEV_PASSWORD)


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
            # Throwaway demo tenants past their expiry. Without this they are
            # only disposable in principle, and a stranger's uploads sit in the
            # database indefinitely.
            if settings.DEMO_SANDBOX:
                from app.services import demo

                demo.sweep_expired(db)
            return fired

    while True:
        await asyncio.sleep(settings.SCHEDULER_INTERVAL)
        try:
            fired = await asyncio.to_thread(tick)
            if fired:
                log.info("scheduler: fired %d workflow(s)", fired)
        except Exception:  # noqa: BLE001 — the scheduler must never die
            log.exception("scheduler tick failed")


async def _keepalive_loop() -> None:
    """Request our own public URL on a timer so a free host never idles out.

    Deliberately its own task rather than another job inside the scheduler
    tick: the two solve unrelated problems, and turning workflow scheduling off
    should not silently stop the thing keeping the site reachable.
    """
    from app.services import keepalive

    while True:
        await asyncio.sleep(max(60, settings.KEEPALIVE_INTERVAL_MINUTES * 60))
        try:
            # In a worker thread: a hanging network call must not block the
            # event loop that is answering real requests.
            await asyncio.to_thread(keepalive.ping_once)
        except Exception:  # noqa: BLE001 — nothing here is worth taking the app down for
            log.exception("keep-alive tick failed")


def _warm_up() -> None:
    """Slow, idempotent startup work that the app does not need in order to
    serve traffic.

    This used to run inline in the lifespan, which meant the platform's health
    check had to wait for ~60 round-trips to a database in another region plus
    seed-corpus indexing before the first request could be answered — and a
    deploy was rejected for exactly that ("timed out waiting for internal
    health check"). Everything here is safe to finish a few seconds late, so
    it runs in a worker thread while the app is already up.
    """
    from app.core import storage
    from app.core.database import harden_public_schema

    for step, fn in (("schema hardening", harden_public_schema),
                     ("seed", _seed_if_empty),
                     ("storage bucket", storage.ensure_bucket)):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — warm-up must never take the app down
            log.warning("warm-up step '%s' failed: %s", step, exc)
    log.info("warm-up complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Blocking, because nothing works without a schema — but this is only
    # CREATE TABLE / ADD COLUMN, which is fast.
    init_db()
    _bootstrap_admin()

    warm = asyncio.create_task(asyncio.to_thread(_warm_up))
    task = asyncio.create_task(_schedule_loop()) if settings.SCHEDULER_ENABLED else None

    # Keep-alive: only when a public URL is configured, and never when it is
    # misconfigured — a keep-alive that silently does nothing is worse than
    # none, because you stop looking for the real cause.
    from app.services import keepalive

    problem = keepalive.configuration_problem()
    if problem:
        log.warning("keep-alive disabled: %s", problem)
    alive = asyncio.create_task(_keepalive_loop()) if keepalive.enabled() else None
    if alive:
        log.info("keep-alive ON — pinging %s every %d min",
                 settings.KEEPALIVE_URL, settings.KEEPALIVE_INTERVAL_MINUTES)

    log.info("EAIOS %s serving — llm=%s scheduler=%s (warm-up in background)",
             settings.VERSION, settings.LLM_PROVIDER, "on" if task else "off")
    # Say this out loud at boot: whether new signups must prove their address
    # is the kind of setting people assume is on and discover is off.
    if settings.REQUIRE_EMAIL_VERIFICATION:
        log.info("email verification ON — codes via %s",
                 "Resend" if settings.RESEND_API_KEY else
                 f"SMTP {settings.SMTP_HOST}" if settings.SMTP_HOST else "server log (!)")
    else:
        log.warning("email verification OFF — set RESEND_API_KEY (or SMTP_HOST) + "
                    "MAIL_FROM to require new signups to prove their address")
    yield
    for t in (task, warm, alive):
        if t:
            t.cancel()


# Refuse to start a production deployment that is signing tokens with the
# public default secret — failing loudly beats running insecurely in silence.
from app.core.config import verify_production_secrets  # noqa: E402

_problems = verify_production_secrets(settings)
if _problems:
    raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(_problems))

# Interactive API docs are useful in development and an information map in
# production, so they are switched off there.
app = FastAPI(
    title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)


# ── error handling ───────────────────────────────────────────────────────
# Clients get a generic message and a correlation id; the server keeps the
# stack trace. Without this, an unhandled database error can echo table names,
# file paths or connection strings straight back to the caller.
@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    ref = uuid.uuid4().hex[:12]
    log.exception("unhandled error ref=%s %s %s", ref, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. "
                           f"Quote reference {ref} if you contact support.", "ref": ref},
    )


def database_error_shape(exc: BaseException) -> dict[str, str]:
    """What went wrong, in terms safe to hand to whoever is looking at it.

    "A database error occurred. Quote reference 7f85584033d2" is useless to
    everyone: the person reading it cannot act, and whoever has to fix it needs
    server logs to learn anything at all. That cost real time on a failure that
    was reproducible in one click.

    So the response now names the exception class and the database object the
    error was about — a constraint, index or column. Those are structural: the
    same category of fact the schema health probe already returns. The *values*
    are what would be sensitive, and PostgreSQL puts those in a DETAIL line
    ("Key (email)=(someone@example.com) already exists"), which is dropped.
    """
    import re

    shape = {"cause": type(exc).__name__}
    original = getattr(exc, "orig", None) or exc

    # Everything up to DETAIL/HINT: the statement-level complaint, no row data.
    text = str(original).split("DETAIL:")[0].split("HINT:")[0].strip()
    text = re.sub(r"\s+", " ", text)[:200]
    if text:
        shape["cause_detail"] = text

    # The object the database named, if it named one. Most specific first —
    # "column X of relation Y" is a complaint about Y, and taking whichever
    # match came first in the string would report the column instead.
    whole = str(original)
    for kind in ("constraint", "index", "relation", "table", "column"):
        named = re.search(rf'{kind} "([^"]+)"', whole)
        if named:
            shape["database_object"] = named.group(1)
            break

    return shape


@app.exception_handler(SQLAlchemyError)
async def _db_error(request: Request, exc: SQLAlchemyError):
    ref = uuid.uuid4().hex[:12]
    log.exception("database error ref=%s %s %s", ref, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "A database error occurred. "
                           f"Quote reference {ref} if you contact support.",
                 "ref": ref, **database_error_shape(exc)},
    )


@app.exception_handler(LimitReached)
async def _plan_limit(request: Request, exc: LimitReached):
    """A plan limit is not a failure — it is the moment to offer the upgrade.

    402 Payment Required is the honest status here, and the body carries what
    was hit, what the current plan allows and what the next one would, so the
    interface can make an offer instead of showing a dead end.
    """
    return JSONResponse(status_code=402, content=exc.as_payload())


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    """Report which field failed and why, without echoing the submitted value
    back (it may contain a password or other sensitive input)."""
    fields = []
    for err in exc.errors()[:8]:
        loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query"))
        fields.append({"field": loc or "body", "problem": err.get("msg", "invalid")})
    return JSONResponse(status_code=422, content={"detail": "Invalid input.", "errors": fields})


# Middleware order is bottom-up: the last one added is the outermost. Security
# headers go outermost-but-one so they are attached to *every* response,
# including 429s and errors; CORS stays outermost so those still carry it.
from app.core.headers import SecurityHeadersMiddleware  # noqa: E402
from app.core.ratelimit import RateLimitMiddleware  # noqa: E402

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # explicit whitelist, never "*"
    allow_credentials=True,
    # Only the verbs and headers this API actually uses — a wildcard would
    # permit method/header combinations no endpoint needs.
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["Retry-After"],
    max_age=600,
)

for router in (
    auth.router, users.router, documents.router, chat.router, agents.router,
    admin.router, analytics.router, graph.router, workflows.router, traces.router,
    reports.router, dashboards.router, studio.router, connectors.router,
    tasks.router, search.router, me.router, orgs.router, ws.router,
):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    """Liveness probe. Deliberately cheap and incapable of hanging.

    The platform polls this to decide whether a deploy succeeded, so it must
    answer immediately even on a cold instance. Resolving the LLM provider can
    involve a network probe (auto-detecting a local model), so a failure or a
    slow reply there is reported rather than allowed to stall the check.
    """
    info: dict = {"status": "ok", "version": settings.VERSION}
    try:
        from app.llm.provider import get_llm

        llm = get_llm()
        info["llm_provider"] = llm.name
        info["llm_model"] = getattr(llm, "model", None)
    except Exception:  # noqa: BLE001 — never let provider detection fail the probe
        info["llm_provider"] = "initialising"
    return info


@app.get("/api/health/schema")
def schema_health():
    """Is the live database's shape still the shape the code expects?

    This exists because of a failure that was invisible from outside. A column
    that stopped being globally unique in the models went on being globally
    unique in the deployed database — ``create_all`` creates missing tables but
    never alters an index that already exists — so the second workspace to pick
    an industry got "a database error occurred" and nothing else. Every test
    passed, because a test database is built fresh from today's models and
    never had the old index. Diagnosing it needed server logs.

    So the schema now reports on itself. The response carries index metadata
    only — no rows, no configuration, no secrets — which is why it needs no
    credentials: the point is to be readable at the moment something is wrong,
    including from a phone.
    """
    from app.core import database as db

    try:
        drifted = db.stale_global_uniques()
        uncascaded = db.missing_cascades()
    except Exception as exc:  # noqa: BLE001 — a probe must not fail
        return {"status": "unknown", "version": settings.VERSION, "error": str(exc)[:200]}

    problems = []
    if drifted:
        problems.append("columns still enforced as globally unique that should be "
                        "unique per workspace")
    if uncascaded:
        problems.append("foreign keys that should cascade on delete but do not, so "
                        "deleting a parent fails whenever a child exists")

    return {
        "status": "ok" if not problems else "drifted",
        "version": settings.VERSION,
        "stale_global_uniques": drifted,
        "missing_cascades": uncascaded,
        "detail": (
            "Schema matches the models."
            if not problems else
            "Found " + "; and ".join(problems)
            + ". Restart the service to repair them; the repair runs on every boot."
        ),
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

    class _CachingStatic(StaticFiles):
        """Cache the fingerprinted bundle forever, never the HTML shell.

        Vite emits content-hashed filenames under ``/assets`` — the name changes
        whenever the bytes do, so a repeat visitor can reuse them without
        re-validating (this was a full 861 KB re-check on every load). index.html
        is the opposite: it points at whichever hashes are current, so it must be
        revalidated every time or a deploy would serve stale asset references.
        """

        async def get_response(self, path: str, scope):
            resp = await super().get_response(path, scope)
            if path.startswith("assets/") or "/assets/" in path:
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path in ("", ".", "index.html") or path.endswith(".html"):
                resp.headers["Cache-Control"] = "no-cache"
            return resp

    app.mount("/", _CachingStatic(directory=_static_dir, html=True), name="spa")
    log.info("Single-container mode: serving frontend from %s", _static_dir)
