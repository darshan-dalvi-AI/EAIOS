"""Analytics Agent — computes platform metrics and narrates business insights."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.agents.base import AgentResult, BaseAgent
from app.models import AgentRun, Document, Message, User


class AnalyticsAgent(BaseAgent):
    id = "analytics"
    name = "Analytics Agent"
    description = "Computes usage metrics and generates plain-language business insights."
    capabilities = ["Usage metrics", "Trend narration", "Agent performance", "Adoption insights"]

    def _run(self, task: str) -> AgentResult:
        db = self.db
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        users = db.scalar(select(func.count()).select_from(User)) or 0
        docs = db.scalar(select(func.count()).select_from(Document)) or 0
        indexed = db.scalar(select(func.count()).select_from(Document).where(Document.status == "indexed")) or 0
        msgs_7d = db.scalar(select(func.count()).select_from(Message).where(Message.created_at >= week_ago)) or 0
        runs = db.execute(
            select(AgentRun.agent, func.count()).group_by(AgentRun.agent).order_by(func.count().desc())
        ).all()
        avg_ms = db.scalar(select(func.avg(AgentRun.duration_ms))) or 0

        top = ", ".join(f"{agent} ({count} runs)" for agent, count in runs[:3]) or "no agent activity yet"
        index_rate = f"{(indexed / docs * 100):.0f}%" if docs else "n/a"

        answer = (
            f"Platform snapshot: {users} registered users, {docs} documents ({indexed} indexed, {index_rate} success rate), "
            f"and {msgs_7d} chat messages in the last 7 days. Most active agents: {top}. "
            f"Mean agent latency is {avg_ms:.0f} ms. "
            + ("Document engagement is healthy — consider enabling more connectors." if msgs_7d > 10
               else "Usage is still ramping up — seed more documents and invite teammates to lift engagement.")
        )
        return AgentResult(answer=answer, confidence=90)
