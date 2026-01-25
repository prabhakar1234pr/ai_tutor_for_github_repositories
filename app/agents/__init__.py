"""
Roadmap generation agent module.
This contains the LangGraph agent that generates learning roadmaps.
"""

from app.agents.state import (
    ConceptData,
    DayTheme,
    RepoAnalysis,
    RoadmapAgentState,
    TaskData,
)


# NOTE:
# Keep this package import side-effect free.
# Importing `app.agents` should not eagerly import `roadmap_agent` (which pulls in nodes/services)
# to avoid circular imports (e.g., services importing pydantic models under app.agents).
def get_roadmap_graph():  # type: ignore[no-untyped-def]
    from app.agents.roadmap_agent import get_roadmap_graph as _get

    return _get()


def build_roadmap_graph():  # type: ignore[no-untyped-def]
    from app.agents.roadmap_agent import build_roadmap_graph as _build

    return _build()


async def run_roadmap_agent(*args, **kwargs):  # type: ignore[no-untyped-def]
    from app.agents.roadmap_agent import run_roadmap_agent as _run

    return await _run(*args, **kwargs)


__all__ = [
    # State types
    "RoadmapAgentState",
    "RepoAnalysis",
    "DayTheme",
    "ConceptData",
    "TaskData",
    # Main agent
    "get_roadmap_graph",
    "run_roadmap_agent",
    "build_roadmap_graph",
]
