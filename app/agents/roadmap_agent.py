"""
LangGraph nodes for roadmap generation.
Each node performs a specific step in the content generation pipeline.
"""

# We'll uncomment these as we create each node file

# from app.agents.nodes.fetch_context import fetch_project_context
# from app.agents.nodes.analyze_repo import analyze_repository
# from app.agents.nodes.plan_curriculum import plan_and_save_curriculum
# from app.agents.nodes.generate_day0 import generate_day0_content, save_day0_content
# from app.agents.nodes.generate_content import (
#     select_next_day,
#     generate_concepts_for_day,
#     generate_subconcepts_and_tasks,
# )
# from app.agents.nodes.database import (
#     insert_all_days_to_db,
#     save_concepts_to_db,
#     mark_day_generated,
#     update_project_status,
# )

__all__ = [
    # Context & Analysis
    # "fetch_project_context",
    # "analyze_repository",
    
    # Planning
    # "plan_and_save_curriculum",
    # "insert_all_days_to_db",
    
    # Day 0 Generation
    # "generate_day0_content",
    # "save_day0_content",
    
    # Content Generation (Days 1-N)
    # "select_next_day",
    # "generate_concepts_for_day",
    # "generate_subconcepts_and_tasks",
    # "save_concepts_to_db",
    # "mark_day_generated",
    
    # Status Management
    # "update_project_status",
]