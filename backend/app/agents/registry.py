"""Static agent registry — metadata without instantiation."""
from app.agents.analytics_agent import AnalyticsAgent
from app.agents.coding_agent import CodingAgent
from app.agents.document_agent import DocumentAgent
from app.agents.email_agent import EmailAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.planning_agent import PlanningAgent
from app.agents.report_agent import ReportAgent
from app.agents.research_agent import ResearchAgent
from app.agents.sql_agent import SQLAgent

AGENT_CLASSES = [
    PlanningAgent,
    DocumentAgent,
    SQLAgent,
    ResearchAgent,
    EmailAgent,
    ReportAgent,
    AnalyticsAgent,
    MemoryAgent,
    CodingAgent,
]

AGENT_MAP = {cls.id: cls for cls in AGENT_CLASSES}


def all_agents():
    return AGENT_CLASSES
