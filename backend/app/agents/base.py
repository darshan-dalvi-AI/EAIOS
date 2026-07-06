"""Agent contract: every agent takes (db, user), executes a task, and records
an AgentRun row for observability."""
import json
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import AgentRun, User
from app.schemas import Citation


@dataclass
class AgentResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: int = 70  # 0-100

    @property
    def citations_json(self) -> str:
        return json.dumps([c.model_dump() for c in self.citations])


class BaseAgent:
    id: str = "base"
    name: str = "Base Agent"
    description: str = ""
    capabilities: list[str] = []

    def __init__(self, db: Session, user: User) -> None:
        self.db = db
        self.user = user

    def run(self, task: str) -> AgentResult:
        start = time.perf_counter()
        status = "ok"
        try:
            result = self._run(task)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            result = AgentResult(answer=f"{self.name} encountered an error: {exc}", confidence=10)
        duration_ms = int((time.perf_counter() - start) * 1000)
        self.db.add(AgentRun(
            agent=self.id,
            user_id=self.user.id,
            status=status,
            input=task[:1000],
            output=result.answer[:2000],
            duration_ms=duration_ms,
        ))
        self.db.commit()
        return result

    def _run(self, task: str) -> AgentResult:
        raise NotImplementedError
