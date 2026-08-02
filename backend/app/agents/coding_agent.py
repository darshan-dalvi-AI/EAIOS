"""Coding Agent — explains, generates, reviews, and debugs code.

Grounded in the knowledge base when relevant (e.g. the engineering handbook
or product manuals contain commands/config), otherwise pure LLM reasoning.
The mock LLM returns a deterministic, viva-safe response."""
from app.agents.base import AgentResult, BaseAgent
from app.llm.provider import NO_MODEL_PREFIX, safe_complete
from app.rag.retrieval import hybrid_search

SYSTEM = (
    "You are the CODING Agent of K-OS, a senior software engineer. "
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

    # Retrieval always returns its best k chunks, even when the best is poor.
    # For a coding question that means an unrelated contract clause gets
    # prepended as "CONTEXT" and the model treats it as relevant — observed in
    # production, where a question about a client SOW came back quoting a
    # service-credit clause at the user. Weak matches are worse than none here,
    # so anything below this similarity is dropped.
    MIN_RELEVANCE = 0.35

    def _run(self, task: str) -> AgentResult:
        retrieved = [r for r in hybrid_search(self.db, task, k=2)
                     if r.score >= self.MIN_RELEVANCE]
        context = "\n\n".join(r.text for r in retrieved)
        prompt = f"CONTEXT:\n{context}\n\nREQUEST: {task}" if context else f"REQUEST: {task}"
        answer = safe_complete(SYSTEM, prompt)

        # Confidence was a hard-coded 78 regardless of what came back — including
        # when the answer was the mock engine's "I cannot compose that" notice.
        # A platform whose whole claim is honest, visible uncertainty cannot
        # report 78% on a non-answer.
        if answer.startswith(NO_MODEL_PREFIX):
            confidence = 15
        elif retrieved:
            avg = sum(r.score for r in retrieved) / len(retrieved)
            confidence = min(90, int(60 + 30 * avg))
        else:
            confidence = 70          # unsourced but genuine model reasoning
        return AgentResult(answer=answer, confidence=confidence)
