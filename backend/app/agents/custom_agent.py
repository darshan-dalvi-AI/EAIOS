"""Runtime for Agent Studio's no-code custom agents.

A CustomAgent row (name + system prompt + enabled tools) is wrapped in the
same BaseAgent contract as the built-in fleet, so it records AgentRun
telemetry and can be invoked from Chat's route picker exactly like any
first-class agent. Enabled tools:
  · rag — hybrid_search over the knowledge base is prepended as CONTEXT
  · web — a DuckDuckGo lookup (reuses the Research agent's fetcher) is added
"""
import json

from app.agents.base import AgentResult, BaseAgent
from app.core.tracing import span
from app.llm.provider import safe_complete
from app.models import CustomAgent as CustomAgentRow
from app.rag.retrieval import hybrid_search
from app.schemas import Citation


class CustomAgentRunner(BaseAgent):
    """Not registered statically — instantiated from a CustomAgent row."""

    def __init__(self, db, user, row: CustomAgentRow) -> None:
        super().__init__(db, user)
        self.id = row.slug
        self.name = row.name
        self.description = row.description
        self.system_prompt = row.system_prompt
        try:
            self.tools = set(json.loads(row.tools or "[]"))
        except Exception:  # noqa: BLE001
            self.tools = set()
        self._row_id = row.id

    def _run(self, task: str) -> AgentResult:
        context_parts: list[str] = []
        citations: list[Citation] = []

        if "rag" in self.tools:
            with span("hybrid_search", kind="retrieval", query=task[:100]) as s:
                hits = hybrid_search(self.db, task, k=5)
                if s is not None:
                    s["attrs"]["hits"] = len(hits)
            if hits:
                context_parts.append("KNOWLEDGE BASE:\n" + "\n\n".join(
                    f"[{i + 1}] {h.title}" + (f" — {h.section}" if h.section else "") + f"\n{h.text}"
                    for i, h in enumerate(hits)))
                citations = [Citation(doc_id=h.doc_id, title=h.title,
                                      section=h.section or f"p.{h.page}", score=h.score) for h in hits]

        if "web" in self.tools:
            try:
                from app.agents.research_agent import ResearchAgent

                web = ResearchAgent(self.db, self.user)._run(task)  # noqa: SLF001
                if web and web.answer:
                    context_parts.append(f"WEB SEARCH:\n{web.answer}")
            except Exception:  # noqa: BLE001 — web tool is best-effort
                pass

        context = "\n\n".join(context_parts)
        prompt = f"{context}\n\nUSER REQUEST: {task}" if context else task
        system = self.system_prompt
        if "rag" in self.tools:
            system += " Ground your answer in the KNOWLEDGE BASE context when present and cite sources as [1], [2]."

        with span("llm.complete", kind="llm", chars=len(prompt)):
            answer = safe_complete(system, prompt)

        confidence = 80 if context_parts else 68
        return AgentResult(answer=answer, citations=citations[:8], confidence=confidence)


def load_runner(db, user, slug: str) -> CustomAgentRunner | None:
    from sqlalchemy import select

    row = db.scalar(select(CustomAgentRow).where(CustomAgentRow.slug == slug, CustomAgentRow.enabled == True))  # noqa: E712
    return CustomAgentRunner(db, user, row) if row else None
