"""
Curriculum planning prompt template.
Generates complete curriculum with days, concepts, and dependency graph.
"""

CURRICULUM_PLANNING_PROMPT = """You are a curriculum designer creating a {target_days}-day learning roadmap for rebuilding a GitHub project.

**Project Analysis:**
{repo_analysis}

**Student Profile:**
- Skill Level: {skill_level}
- Target Duration: {target_days} days
- Repository: {github_url}

**Your Task:**
Create a complete curriculum with ALL concepts defined upfront. Each day has 2-4 learning concepts.

**Requirements:**
- Day 0 is ALWAYS "Project Setup & GitHub Connection" (already provided, skip in your output)
- Days 1 to {last_day_number} should progress logically from basics to advanced
- Each day should have 2-4 concepts that build on each other
- Concepts should reference specific files/directories in the repo (repo_anchors)
- Define dependencies between concepts (which concepts must be completed first)
- Match the {skill_level} skill level
- Each concept should take 15-45 minutes to learn

**Concept IDs:**
- Use simple IDs like "c1", "c2", "c3", etc.
- IDs must be unique across the entire curriculum

**Return ONLY valid JSON object with this structure:**
{{
  "days": [
    {{
      "day_number": 1,
      "theme": "Short descriptive theme (5-8 words)",
      "description": "1-2 sentences explaining what the student will learn",
      "concept_ids": ["c1", "c2", "c3"]
    }},
    ...
    {{
      "day_number": {last_day_number},
      "theme": "...",
      "description": "...",
      "concept_ids": ["cX", "cY"]
    }}
  ],
  "concepts": {{
    "c1": {{
      "title": "Concept title",
      "objective": "What the student will learn",
      "repo_anchors": ["src/main.py", "src/config/"],
      "depends_on": [],
      "difficulty": "easy"
    }},
    "c2": {{
      "title": "...",
      "objective": "...",
      "repo_anchors": ["..."],
      "depends_on": ["c1"],
      "difficulty": "medium"
    }}
  }},
  "dependency_graph": {{
    "c1": ["c2", "c3"],
    "c2": ["c4"]
  }}
}}

**CRITICAL:**
- Return ONLY the JSON object, no markdown formatting
- Start from day 1 (Day 0 is handled separately)
- Include exactly {last_day_number} days
- Every concept_id in days must exist in concepts object
- repo_anchors should be actual file paths or directories from the project
- difficulty must be one of: "easy", "medium", "hard"
- depends_on should reference concept IDs that must be completed first
- dependency_graph shows which concepts unlock other concepts (parent -> children)
"""
