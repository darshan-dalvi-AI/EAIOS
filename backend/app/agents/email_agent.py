"""Email Agent — professional email drafting, optionally grounded in the knowledge base."""
from app.agents.base import AgentResult, BaseAgent
from app.llm.provider import safe_complete
from app.rag.retrieval import hybrid_search

SYSTEM = (
    "You are the EMAIL Agent of EAIOS. Draft a clear, professional business email for the user's request. "
    "Use any provided CONTEXT for factual details. Include a subject line."
)


class EmailAgent(BaseAgent):
    id = "email"
    name = "Email Agent"
    description = "Drafts professional emails and replies, grounded in enterprise context when relevant."
    capabilities = ["Email drafting", "Reply generation", "Tone control", "Context grounding"]

    def _run(self, task: str) -> AgentResult:
        retrieved = hybrid_search(self.db, task, k=2)
        context = "\n\n".join(r.text for r in retrieved)
        prompt = (f"CONTEXT:\n{context}\n\nQUESTION: {task}" if context else f"QUESTION: {task}")
        return AgentResult(answer=safe_complete(SYSTEM, prompt), confidence=80)
