"""Relational schema — users, documents, chat, agents, memory, audit."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, LargeBinary,
    String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# A timezone-aware UTC timestamp. Postgres stores it as ``timestamptz`` and
# hands it back tz-aware, so a value read from the database can be compared to
# ``datetime.now(timezone.utc)`` directly — no per-read normalisation, no
# "can't compare naive and aware" surprise waiting for the next caller.
_UTCDateTime = DateTime(timezone=True)

from app.core.database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    """A tenant — one company/customer. Every other row belongs to exactly one
    organization; queries are auto-scoped to the caller's org (see database.py)."""
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | pro | enterprise
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    # Which industry profile configured this workspace (see services/industries).
    # Empty = the onboarding picker has not been answered yet.
    industry: Mapped[str] = mapped_column(String(40), default="")
    # A throwaway workspace handed to a visitor trying the product. Everything
    # inside is real — uploads index, agents answer, limits apply — but the
    # whole tenant is deleted when it expires, so nothing a stranger does
    # survives into the next visitor's session or into the database long-term.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Compared against now() to expire demo workspaces — tz-aware so the
    # comparison never depends on the reader remembering to attach UTC.
    expires_at: Mapped[datetime | None] = mapped_column(_UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class TenantMixin:
    """Adds an ``org_id`` to a model. The session layer auto-filters SELECTs and
    auto-stamps INSERTs by the current org, so tenant isolation can't be
    forgotten per-query. Nullable so unscoped/system inserts fail safe (an
    unstamped row is invisible to every tenant) rather than erroring."""
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True, default=None)


class User(TenantMixin, Base):
    __tablename__ = "users"
    # Role drives every authorization decision, so the set of legal values is
    # enforced by the database itself — not only by the API's Literal type. A
    # stray write (a bug, a migration, a console fix) can't mint role='owner'.
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'hr', 'manager', 'employee')",
                        name="ck_users_role"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="employee")  # admin | hr | manager | employee
    avatar_hue: Mapped[int] = mapped_column(Integer, default=210)
    is_active: Mapped[bool] = mapped_column(default=True)
    # ── email ownership ──────────────────────────────────────────────
    # Anyone can type an address; these prove they can receive at it.
    # Google sign-in sets verified immediately (Google asserts it);
    # password signup stays false until the emailed code is entered.
    email_verified: Mapped[bool] = mapped_column(default=False)
    auth_provider: Mapped[str] = mapped_column(String(20), default="password")  # password | google
    verify_code_hash: Mapped[str | None] = mapped_column(String(200), default=None)
    # Compared against now() when a code is entered — tz-aware, same reason.
    verify_expires_at: Mapped[datetime | None] = mapped_column(_UTCDateTime, default=None)
    verify_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Tokens are stateless, so "log out everywhere" needs a server-side epoch:
    # any token whose ``iat`` predates this value is refused. Logout (and a
    # future password reset) bumps it, instantly retiring every token already
    # issued for this account — the break-glass a stateless JWT otherwise lacks.
    token_epoch: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    last_login: Mapped[datetime | None] = mapped_column(default=None)

    documents: Mapped[list["Document"]] = relationship(back_populates="owner")


class Document(TenantMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    filename: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str] = mapped_column(String(20))          # pdf | docx | pptx | xlsx | csv | image | txt
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | processing | indexed | failed
    error: Mapped[str | None] = mapped_column(Text, default=None)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    owner: Mapped[User] = relationship(back_populates="documents")
    # Deliberately NOT passive_deletes: that would hand every cascade to the
    # database, and SQLite does not enforce foreign keys unless asked, so a
    # local run would silently leave orphaned chunks behind. The two mechanisms
    # cover different paths — the ORM cascade handles ``db.delete(document)``,
    # the database's ON DELETE CASCADE handles bulk ``DELETE ... WHERE id IN``,
    # which never loads the children to begin with.
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan")


class Chunk(TenantMixin, Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    # ON DELETE CASCADE is load-bearing, not tidiness. Starter documents are
    # indexed in the background, so a chunk can be written moments after the
    # visitor swaps industry and deletes its document. Deleting chunks first
    # and documents second leaves a window between the two statements; a chunk
    # arriving in that window makes the second statement violate this key, and
    # the visitor sees "a database error occurred". Letting the database remove
    # the children closes the window — there is no longer a gap to lose.
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ord: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(String(255), default="")
    page: Mapped[int] = mapped_column(Integer, default=0)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(TenantMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(TenantMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))               # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    agent: Mapped[str] = mapped_column(String(40), default="")  # which agent produced it
    citations: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of {doc_id,title,section,score}
    confidence: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    created_at: Mapped[datetime] = mapped_column(default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AgentRun(TenantMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | error
    input: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class MemoryEntry(TenantMixin, Base):
    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))               # preference | fact | project
    content: Mapped[str] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    last_used: Mapped[datetime] = mapped_column(default=_now)


class AuditLog(TenantMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    # Deliberately NOT a foreign key: the trail is append-only and has to
    # outlive the account it describes.
    user_id: Mapped[str | None] = mapped_column(String(32), default=None)
    # Captured at write time so the entry still names a person after they are
    # removed from the workspace. An audit log that forgets who did something
    # the moment they leave is worthless precisely when it is needed most.
    actor_email: Mapped[str] = mapped_column(String(200), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)


# ── knowledge graph ──────────────────────────────────────────────────────
class Entity(TenantMixin, Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(200), index=True)  # normalized name (unique per org, not global)
    etype: Mapped[str] = mapped_column(String(20), default="term")  # person|org|money|date|acronym|concept|term
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class EntityEdge(TenantMixin, Base):
    __tablename__ = "entity_edges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    weight: Mapped[int] = mapped_column(Integer, default=1)   # co-occurrence count
    doc_id: Mapped[str | None] = mapped_column(String(32), default=None, index=True)


class EntityMention(TenantMixin, Base):
    __tablename__ = "entity_mentions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(String(32), index=True)
    document_id: Mapped[str] = mapped_column(String(32), index=True)


# ── workflows (Automations app) ──────────────────────────────────────────
class Workflow(TenantMixin, Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300), default="")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | upload | schedule
    nodes: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{id,type,x,y,data}]
    edges: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{from,to}]
    enabled: Mapped[bool] = mapped_column(default=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class WorkflowRun(TenantMixin, Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | ok | error
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    input: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    log: Mapped[str] = mapped_column(Text, default="[]")  # JSON per-node entries
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    pending: Mapped[str] = mapped_column(Text, default="")  # JSON checkpoint when status=awaiting_approval (HITL)
    created_at: Mapped[datetime] = mapped_column(default=_now)


# ── structured data tables (advanced document parsing → SQL agent) ───────
class DataTable(TenantMixin, Base):
    """A table extracted from an uploaded document, materialized as a REAL
    SQL table (``dt_<doc>_<n>``) so the SQL Agent can query it directly —
    structured data bypasses text chunking entirely."""

    __tablename__ = "data_tables"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(String(32), index=True)
    doc_title: Mapped[str] = mapped_column(String(255), default="")
    table_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # physical SQL table
    title: Mapped[str] = mapped_column(String(200), default="")   # e.g. "Sheet1", "p.3 table 1"
    columns: Mapped[str] = mapped_column(Text, default="[]")      # JSON [{name,type}]
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="")   # pdf | xlsx | csv | docx | pptx | txt
    created_at: Mapped[datetime] = mapped_column(default=_now)


# ── graph checkpoints (LangGraph-style state persistence) ────────────────
class GraphCheckpoint(TenantMixin, Base):
    """Orchestrator graph state persisted after every super-step, keyed by
    thread (conversation). Interrupted runs resume from the saved node."""

    __tablename__ = "graph_checkpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    state: Mapped[str] = mapped_column(Text, default="{}")        # JSON graph state
    next_node: Mapped[str] = mapped_column(Text, default="")      # JSON: "node" | ["a","b"] | "__end__"
    status: Mapped[str] = mapped_column(String(12), default="running")  # running | interrupted | done
    steps: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


# ── Agent Studio (no-code custom agents) ─────────────────────────────────
class CustomAgent(TenantMixin, Base):
    """A user-authored agent: a name, a system prompt, and a set of enabled
    tools (rag / web). Runs through the same BaseAgent contract as the
    built-in fleet and is invocable from Chat's route picker."""

    __tablename__ = "custom_agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    slug: Mapped[str] = mapped_column(String(60), index=True)  # route id (unique per org, not global)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300), default="")
    system_prompt: Mapped[str] = mapped_column(Text)
    tools: Mapped[str] = mapped_column(String(200), default="[]")  # JSON list: ["rag","web"]
    hue: Mapped[int] = mapped_column(Integer, default=265)
    enabled: Mapped[bool] = mapped_column(default=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


# ── Connectors (Gmail / Drive / sample workspace → RAG) ──────────────────
class Connector(TenantMixin, Base):
    """A configured data source. Syncing pulls items from the provider and
    feeds them through the same ingestion pipeline as uploaded documents."""

    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    provider: Mapped[str] = mapped_column(String(30))  # sample | google_drive | gmail
    label: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="disconnected")  # disconnected | connected | syncing | error
    detail: Mapped[str] = mapped_column(Text, default="")     # last sync summary / error
    synced_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)


# ── Saved dashboards (NL-to-BI charts) ───────────────────────────────────
class SavedChart(TenantMixin, Base):
    """A pinned natural-language chart: the question, the generated SQL, the
    chart spec and a snapshot of the result so a dashboard renders instantly."""

    __tablename__ = "saved_charts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(String(400))
    sql: Mapped[str] = mapped_column(Text, default="")
    spec: Mapped[str] = mapped_column(Text, default="{}")     # JSON {type,x,y,columns,rows}
    created_at: Mapped[datetime] = mapped_column(default=_now)


# ── Collaborative code workspace (Code app) ─────────────────────────────
class Project(TenantMixin, Base):
    """A code project inside a workspace — the unit several people edit together.

    Deliberately a first-class tenant object: a project belongs to exactly one
    organization, so the same isolation that protects documents protects source
    code, including the database-level RLS policy (which is derived from every
    model carrying ``org_id``)."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400), default="")
    language: Mapped[str] = mapped_column(String(30), default="python")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    files: Mapped[list["ProjectFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan")


class ProjectFile(TenantMixin, Base):
    """One file. ``content`` is the last persisted text; ``ydoc`` is the binary
    CRDT state that lets concurrent editors converge without overwriting each
    other. Text is kept alongside so search, diffing and the agents can read a
    file without a CRDT client."""

    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(300))          # e.g. "src/main.py"
    language: Mapped[str] = mapped_column(String(30), default="plaintext")
    content: Mapped[str] = mapped_column(Text, default="")
    # Yjs document state vector — binary, written by the collaboration server.
    ydoc: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    updated_by: Mapped[str | None] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    project: Mapped[Project] = relationship(back_populates="files")
    # Same two-mechanism cascade as Document→Chunk: the ORM relationship handles
    # a delete that goes through the session (deleting a project deletes its
    # files, which must delete their history), and the ON DELETE CASCADE on the
    # column above handles a bulk `DELETE ... WHERE id IN`, which never loads
    # the children. Relying on only one of them orphans rows — on SQLite,
    # silently, because it does not enforce foreign keys by default.
    versions: Mapped[list["FileVersion"]] = relationship(
        back_populates="file", cascade="all, delete-orphan")


class FileVersion(TenantMixin, Base):
    """An immutable snapshot of a file's text. Written on explicit save and
    periodically during a collaborative session, so concurrent editing can never
    lose work permanently — there is always a point to roll back to."""

    __tablename__ = "file_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("project_files.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str | None] = mapped_column(String(32), default=None)
    author_name: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    file: Mapped[ProjectFile] = relationship(back_populates="versions")


class Task(TenantMixin, Base):
    """Kanban task — created manually or auto-extracted from meeting minutes
    ("action items" bullets become cards). Assignable to any workspace user."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(12), default="todo")  # todo | doing | done
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | meeting
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), default=None, index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class UsageEvent(TenantMixin, Base):
    """One AI request — powers the Admin usage/cost view. Token counts are
    estimated (~4 chars/token) when the provider doesn't report real usage."""

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, default=None)
    kind: Mapped[str] = mapped_column(String(20), default="chat")  # chat | studio | workflow | meeting | sql
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_now, index=True)
