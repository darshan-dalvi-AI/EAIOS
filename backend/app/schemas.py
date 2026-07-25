"""Pydantic request/response contracts."""
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ─────────────────────────────────────────────────────────
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)


class SignupIn(BaseModel):
    """Create a new company workspace + its first admin."""
    company_name: str = Field(min_length=2, max_length=160)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    role: str
    avatar_hue: int
    is_active: bool
    org_id: str | None = None
    created_at: datetime
    last_login: datetime | None = None


class UserUpdate(BaseModel):
    role: Literal["admin", "hr", "manager", "employee"] | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


class UserCreate(BaseModel):
    """Admin 'hire' form — create a manager/employee (or admin) account."""
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "hr", "manager", "employee"] = "employee"


# ── Documents ────────────────────────────────────────────────────
class DocumentOut(ORMModel):
    id: str
    filename: str
    title: str
    doc_type: str
    size_bytes: int
    status: str
    chunk_count: int
    page_count: int
    tags: str
    created_at: datetime


class ChunkOut(ORMModel):
    id: str
    ord: int
    text: str
    section: str
    page: int


# ── Chat ─────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=64)
    agent: str | None = Field(default=None, max_length=64)  # force a specific agent; default → planner routes


class Citation(BaseModel):
    doc_id: str
    title: str
    section: str = ""
    score: float = 0.0


class MessageOut(ORMModel):
    id: str
    role: str
    content: str
    agent: str
    citations: str
    confidence: int
    created_at: datetime


class ConversationOut(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatOut(BaseModel):
    conversation_id: str
    message: MessageOut
    plan: list[str] = []            # agents invoked, in order
    retrieved: list[Citation] = []


# ── Agents ───────────────────────────────────────────────────────
class AgentInfo(BaseModel):
    id: str
    name: str
    description: str
    capabilities: list[str]


class AgentRunOut(ORMModel):
    id: str
    agent: str
    status: str
    input: str
    output: str
    duration_ms: int
    created_at: datetime


# ── SQL assistant ────────────────────────────────────────────────
class SQLIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class SQLOut(BaseModel):
    sql: str
    explanation: str
    columns: list[str] = []
    rows: list[list] = []
    warning: str = ""


# ── Analytics / admin ────────────────────────────────────────────
class StatsOut(BaseModel):
    users: int
    documents: int
    chunks: int
    conversations: int
    messages: int
    agent_runs: int
    vector_backend: str
    llm_provider: str


class AuditOut(ORMModel):
    id: str
    user_id: str | None
    action: str
    detail: str
    ip: str
    created_at: datetime


class MemoryOut(ORMModel):
    id: str
    kind: str
    content: str
    weight: int
    created_at: datetime


# ── knowledge graph ──────────────────────────────────────────────────────
class GraphNodeOut(BaseModel):
    id: str
    name: str
    type: str
    mentions: int


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    weight: int


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


# ── workflows ────────────────────────────────────────────────────────────
class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    trigger: str = "manual"           # manual | upload | schedule
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    enabled: bool = True


class WorkflowOut(ORMModel):
    id: str
    name: str
    description: str
    trigger: str
    nodes: str    # JSON string (client parses)
    edges: str
    enabled: bool
    run_count: int
    last_run_at: datetime | None
    updated_at: datetime


class WorkflowRunOut(ORMModel):
    id: str
    workflow_id: str
    status: str   # running | ok | error | awaiting_approval
    trigger: str
    input: str
    output: str
    log: str      # JSON string of node entries
    duration_ms: int
    created_at: datetime


class WorkflowRunIn(BaseModel):
    input: str = ""


class WorkflowApprovalIn(BaseModel):
    approved: bool
