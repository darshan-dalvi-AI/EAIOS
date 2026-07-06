"""Lightweight distributed-tracing core (Langfuse/OTel-compatible model).

Every chat request / workflow run becomes a *trace*; agents, retrieval, and
LLM calls become *spans* inside it. Traces live in an in-process ring buffer
served by ``GET /api/traces`` — zero external services required.

If the optional exporters are installed AND configured, spans are mirrored:
- OpenTelemetry: ``pip install opentelemetry-sdk opentelemetry-exporter-otlp``
  + ``OTEL_EXPORTER_OTLP_ENDPOINT`` env.
- Langfuse: ``pip install langfuse`` + ``LANGFUSE_PUBLIC_KEY/SECRET_KEY`` env.
Both are best-effort: failures never affect the request path.
"""
import contextvars
import logging
import os
import time
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("eaios.tracing")

TRACES: deque[dict] = deque(maxlen=200)
_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("eaios_trace", default=None)

# ── optional exporters (never required) ─────────────────────────────────
_otel_tracer = None
try:  # pragma: no cover
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry import trace as _ot
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "eaios-backend"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        _ot.set_tracer_provider(provider)
        _otel_tracer = _ot.get_tracer("eaios")
        log.info("OpenTelemetry OTLP exporter active")
except Exception:  # noqa: BLE001
    _otel_tracer = None

_langfuse = None
try:  # pragma: no cover
    if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
        from langfuse import Langfuse

        _langfuse = Langfuse()
        log.info("Langfuse exporter active")
except Exception:  # noqa: BLE001
    _langfuse = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_trace(name: str, user: str = "", kind: str = "chat") -> dict:
    trace = {
        "id": uuid.uuid4().hex[:12],
        "name": name[:120],
        "kind": kind,
        "user": user,
        "started_at": _now_iso(),
        "_t0": time.perf_counter(),
        "duration_ms": 0,
        "spans": [],
        "status": "ok",
    }
    _current.set(trace)
    return trace


def end_trace(status: str = "ok") -> dict | None:
    trace = _current.get()
    if trace is None:
        return None
    trace["duration_ms"] = int((time.perf_counter() - trace["_t0"]) * 1000)
    trace["status"] = status
    trace.pop("_t0", None)
    TRACES.appendleft({k: v for k, v in trace.items()})
    _current.set(None)
    if _langfuse is not None:  # pragma: no cover
        try:
            lf_trace = _langfuse.trace(name=trace["name"], user_id=trace["user"])
            for s in trace["spans"]:
                lf_trace.span(name=s["name"], metadata=s.get("attrs", {}))
        except Exception:  # noqa: BLE001
            pass
    return trace


@contextmanager
def span(name: str, kind: str = "step", **attrs: Any):
    """Record a span inside the current trace (no-op without an active trace)."""
    trace = _current.get()
    if trace is None:
        yield
        return
    t0 = time.perf_counter()
    record = {
        "name": name[:80],
        "kind": kind,  # agent | llm | retrieval | graph | node | step
        "offset_ms": int((t0 - trace["_t0"]) * 1000),
        "duration_ms": 0,
        "status": "ok",
        "attrs": {k: (str(v)[:200] if not isinstance(v, (int, float, bool)) else v) for k, v in attrs.items()},
    }
    trace["spans"].append(record)
    otel_cm = _otel_tracer.start_as_current_span(name) if _otel_tracer else None  # pragma: no cover
    if otel_cm:  # pragma: no cover
        otel_cm.__enter__()
    try:
        yield record
    except Exception:
        record["status"] = "error"
        raise
    finally:
        record["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        if otel_cm:  # pragma: no cover
            try:
                otel_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass


def current_trace_id() -> str | None:
    trace = _current.get()
    return trace["id"] if trace else None
