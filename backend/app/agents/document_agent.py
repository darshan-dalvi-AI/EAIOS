"""Document Agent — RAG question answering over the enterprise knowledge base.

Graph-augmented: relational questions ("how are X and Y related?") are
enriched with a knowledge-graph context block (connection path + co-mention
evidence) before hitting the LLM.
"""
from app.agents.base import AgentResult, BaseAgent
from app.core.tracing import span
from app.llm.provider import safe_complete
from app.rag.retrieval import hybrid_search
from app.schemas import Citation

SYSTEM = (
    "You are the Document Agent of EAIOS, an enterprise knowledge assistant. "
    "Answer strictly from the provided CONTEXT. Cite sources inline as [1], [2]… "
    "If a KNOWLEDGE GRAPH block is present, use it to explain relationships. "
    "If the context is insufficient, say so plainly instead of guessing."
)


class DocumentAgent(BaseAgent):
    id = "document"
    name = "Document Agent"
    description = "Answers questions and produces summaries grounded in the indexed knowledge base."
    capabilities = ["RAG question answering", "Graph-augmented retrieval", "Source citations", "Confidence scoring"]

    def _run(self, task: str) -> AgentResult:
        with span("hybrid_search", kind="retrieval", query=task[:100]) as s:
            retrieved = hybrid_search(self.db, task, k=6)
            if s is not None:
                s["attrs"]["hits"] = len(retrieved)

        # knowledge-graph augmentation for relational questions
        graph_block = ""
        try:
            from app.services import kgraph

            graph_block = kgraph.relational_context(self.db, task)
        except Exception:  # noqa: BLE001 — augmentation never breaks answering
            graph_block = ""

        if not retrieved and not graph_block:
            return AgentResult(
                answer="The knowledge base is empty or nothing matched. Upload documents in the Knowledge app, then ask again.",
                confidence=20,
            )

        context = "\n\n".join(
            f"[{i + 1}] {r.title}" + (f" — {r.section}" if r.section else "") + (f" (p.{r.page})" if r.page else "") + f"\n{r.text}"
            for i, r in enumerate(retrieved)
        )
        if graph_block:
            context = f"{graph_block}\n\n{context}" if context else graph_block

        with span("llm.complete", kind="llm", chars=len(context)):
            answer = safe_complete(SYSTEM, f"CONTEXT:\n{context}\n\nQUESTION: {task}")

        citations = [
            Citation(doc_id=r.doc_id, title=r.title, section=r.section or f"p.{r.page}", score=r.score)
            for r in retrieved
        ]
        if retrieved:
            avg = sum(r.score for r in retrieved) / len(retrieved)
            confidence = min(95, int(55 + 40 * avg))
        else:
            confidence = 70  # pure-graph answer
        if graph_block:
            confidence = min(96, confidence + 4)
        return AgentResult(answer=answer, citations=citations, confidence=confidence)
