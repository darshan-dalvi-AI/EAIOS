"""Memory Agent — long-term, per-user memory (preferences, facts, projects)."""
import re

from sqlalchemy import select

from app.agents.base import AgentResult, BaseAgent
from app.models import MemoryEntry

REMEMBER = re.compile(r"^(remember( that)?|note that|save this[:,]?)\s*", re.I)


class MemoryAgent(BaseAgent):
    id = "memory"
    name = "Memory Agent"
    description = "Maintains long-term user memory: preferences, facts, and project context."
    capabilities = ["Store preferences", "Recall facts", "Personalization", "Project context"]

    def _run(self, task: str) -> AgentResult:
        match = REMEMBER.match(task.strip())
        if match:
            content = task.strip()[match.end():].strip().rstrip(".")
            if not content:
                return AgentResult(answer="Tell me what to remember, e.g. “Remember that our fiscal year starts in April.”", confidence=40)
            kind = "preference" if re.search(r"\b(prefer|like|always|never|format)\b", content, re.I) else "fact"
            self.db.add(MemoryEntry(user_id=self.user.id, kind=kind, content=content))
            self.db.commit()
            return AgentResult(answer=f"Saved to long-term memory ({kind}): “{content}”. I'll use this to personalize future answers.", confidence=95)

        entries = self.db.scalars(
            select(MemoryEntry).where(MemoryEntry.user_id == self.user.id).order_by(MemoryEntry.created_at.desc()).limit(20)
        ).all()
        if not entries:
            return AgentResult(answer="No long-term memories stored for you yet. Say “remember that …” and I'll keep it.", confidence=60)

        listing = " ".join(f"({e.kind}) {e.content}." for e in entries)
        return AgentResult(answer=f"Here's what I remember about you: {listing}", confidence=88)

    def recall_context(self) -> str:
        """Compact memory string other agents can prepend to prompts."""
        entries = self.db.scalars(
            select(MemoryEntry).where(MemoryEntry.user_id == self.user.id).limit(10)
        ).all()
        return "; ".join(e.content for e in entries)
