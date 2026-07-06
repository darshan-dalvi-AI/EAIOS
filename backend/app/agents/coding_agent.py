"""Coding Agent — explains, generates, reviews, and debugs code.

Grounded in the knowledge base when relevant (e.g. the engineering handbook
or product manuals contain commands/config), otherwise pure LLM reasoning.
The mock LLM returns a deterministic, viva-safe response."""
from app.agents.base import AgentResult, BaseAgent
from app.llm.provider import safe_complete
from app.rag.retrieval import hybrid_search

SYSTEM = (
    "You are the CODING Agent of EAIOS, a senior software engineer. "
    "Explain, generate, review, debug, or optimize code as requested. "
    "Always answer with a short explanation followed by a fenced code block "
    "(```language) when code is involved. Use CONTEXT if it contains relevant "
    "commands, configs, or documentation. Be precise; no filler."
)


class CodingAgent(BaseAgent):
    id = "coding"
    name = "Coding Agent"
    description = "Explains, generates, reviews, and debugs code; grounded in engineering docs when available."
    capabilities = ["Code generation", "Code explanation", "Review & debugging", "Optimization tips"]

    def _run(self, task: str) -> AgentResult:
        retrieved = hybrid_search(self.db, task, k=2)
        context = "\n\n".join(r.text for r in retrieved)
        prompt = f"CONTEXT:\n{context}\n\nREQUEST: {task}" if context else f"REQUEST: {task}"
        return AgentResult(answer=safe_complete(SYSTEM, prompt), confidence=78)
