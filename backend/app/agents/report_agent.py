"""Report Agent — structured markdown reports and executive summaries from indexed sources."""
from app.agents.base import AgentResult, BaseAgent
from app.llm.provider import safe_complete
from app.rag.retrieval import hybrid_search
from app.schemas import Citation

SYSTEM = (
    "You are the REPORT Agent of EAIOS. Produce a structured markdown report "
    "(Executive Summary, Key Findings, Recommendations) strictly from the CONTEXT. Cite sources as [n]."
)


class ReportAgent(BaseAgent):
    id = "report"
    name = "Report Agent"
    description = "Generates structured reports and executive summaries with citations from enterprise sources."
    capabilities = ["Executive summaries", "Structured reports", "Markdown output", "Citations"]

    def _run(self, task: str) -> AgentResult:
        retrieved = hybrid_search(self.db, task, k=8)
        context = "\n\n".join(f"[{i + 1}] {r.title}: {r.text}" for i, r in enumerate(retrieved))
        answer = safe_complete(SYSTEM, f"CONTEXT:\n{context}\n\nQUESTION: Write a report on: {task}")
        citations = [Citation(doc_id=r.doc_id, title=r.title, section=r.section, score=r.score) for r in retrieved]
        return AgentResult(answer=answer, citations=citations, confidence=78 if retrieved else 35)
