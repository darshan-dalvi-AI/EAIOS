"""Research Agent — live web lookup with citations (DuckDuckGo Instant Answer API)."""
from app.agents.base import AgentResult, BaseAgent
from app.schemas import Citation


class ResearchAgent(BaseAgent):
    id = "research"
    name = "Research Agent"
    description = "Performs live internet lookups, summarizes findings, and returns source citations."
    capabilities = ["Web search", "News lookup", "Source citations", "Fact verification"]

    def _run(self, task: str) -> AgentResult:
        try:
            import httpx

            r = httpx.get(
                "https://api.duckduckgo.com/",
                params={"q": task, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:  # noqa: BLE001 — offline / blocked network
            return AgentResult(
                answer="Live web search is unreachable from this environment right now. "
                       "The Research Agent uses the DuckDuckGo Instant Answer API; check outbound network access.",
                confidence=15,
            )

        abstract = (data.get("AbstractText") or "").strip()
        citations: list[Citation] = []
        if data.get("AbstractURL"):
            citations.append(Citation(doc_id="web", title=data.get("AbstractSource", "Source"), section=data["AbstractURL"], score=0.9))

        related = []
        for topic in data.get("RelatedTopics", [])[:4]:
            if isinstance(topic, dict) and topic.get("Text"):
                related.append(topic["Text"])
                if topic.get("FirstURL"):
                    citations.append(Citation(doc_id="web", title=topic["Text"][:60], section=topic["FirstURL"], score=0.6))

        if not abstract and not related:
            return AgentResult(answer=f"No instant-answer results for “{task}”. Try a more specific query.", confidence=30)

        parts = [abstract] if abstract else []
        if related:
            parts.append("Related findings: " + " • ".join(related))
        return AgentResult(answer="\n\n".join(parts), citations=citations, confidence=75)
