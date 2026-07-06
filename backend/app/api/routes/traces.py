"""Traces API — serves the in-process span buffer to the Traces app."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.tracing import TRACES
from app.models import User

router = APIRouter(prefix="/traces", tags=["observability"])


@router.get("")
def list_traces(limit: int = 50, user: User = Depends(get_current_user)):
    out = []
    for trace in list(TRACES)[: min(limit, 200)]:
        out.append({k: v for k, v in trace.items() if k != "spans"} | {"span_count": len(trace["spans"])})
    return out


@router.get("/{trace_id}")
def get_trace(trace_id: str, user: User = Depends(get_current_user)):
    for trace in TRACES:
        if trace["id"] == trace_id:
            return trace
    raise HTTPException(404, "Trace not found (buffer holds the last 200)")
