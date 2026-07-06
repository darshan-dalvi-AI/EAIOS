"""Planning Agent — decomposes multi-intent requests and sequences other agents."""
import re

from app.agents.base import AgentResult, BaseAgent

SPLITTERS = re.compile(r"\b(?:and then|then|and also|; also|, then)\b", re.I)


class PlanningAgent(BaseAgent):
    id = "planning"
    name = "Planning Agent"
    description = "Breaks complex requests into subtasks and coordinates the other agents."
    capabilities = ["Task decomposition", "Agent routing", "Multi-step coordination"]

    def decompose(self, task: str) -> list[str]:
        """Split a compound request into ordered subtasks."""
        parts = [p.strip(" .,") for p in SPLITTERS.split(task) if p.strip(" .,")]
        # SPLITTERS keeps no capture groups content besides delimiters; filter delimiter words
        parts = [p for p in parts if p.lower() not in {"and then", "then", "and also", "also"}]
        return parts if len(parts) > 1 else [task]

    def _run(self, task: str) -> AgentResult:
        subtasks = self.decompose(task)
        if len(subtasks) == 1:
            return AgentResult(answer="This is a single-step request — routing directly to the best agent.", confidence=85)
        listing = " ".join(f"Step {i + 1}: {s}." for i, s in enumerate(subtasks))
        return AgentResult(answer=f"I split this into {len(subtasks)} steps. {listing}", confidence=85)
