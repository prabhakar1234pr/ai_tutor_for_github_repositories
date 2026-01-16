"""
Curriculum planning prompt template.
Generates day-by-day learning themes for the entire roadmap.
"""

CURRICULUM_PLANNING_PROMPT = """You are a curriculum designer creating a {target_days}-day learning roadmap for rebuilding a GitHub project.

**Project Analysis:**
{repo_analysis}

**Student Profile:**
- Skill Level: {skill_level}
- Target Duration: {target_days} days
- Repository: {github_url}

**Your Task:**
Create a {target_days}-day learning plan where each day has a focused theme.

**Requirements:**
- Day 0 is ALWAYS "Project Setup & GitHub Connection" (already provided, skip in your output)
- Days 1 to {last_day_number} should progress logically from basics to advanced
- Each day should build on previous days
- Each day's theme must be clearly distinct from previous days
- Match the {skill_level} skill level
- Each day should take 2-4 hours to complete

**Return ONLY valid JSON array starting from day 1:**
[
  {{
    "day_number": 1,
    "theme": "Short descriptive theme (5-8 words)",
    "description": "1-2 sentences explaining what the student will learn"
  }},
  ...
  {{
    "day_number": {last_day_number},
    "theme": "...",
    "description": "..."
  }}
]

**CRITICAL:**
- Return ONLY the JSON array, no markdown formatting
- Start from day 1 (Day 0 is handled separately)
- Include exactly {last_day_number} days
"""
