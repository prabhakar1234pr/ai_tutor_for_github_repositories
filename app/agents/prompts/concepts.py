"""
Concepts generation prompt template.
Generates learning concepts for a specific day.
"""

CONCEPTS_GENERATION_PROMPT = """You are designing the learning concepts for a specific day in a coding curriculum.

**Day Information:**
- Day Number: {day_number}
- Theme: {day_theme}
- Description: {day_description}
- Skill Level: {skill_level}

**Repository Context:**
{repo_summary}

**Your Task:**
Generate 3-5 major learning concepts for this day.

**Guidelines:**
- Each concept should be a substantial topic worth 20-40 minutes of reading
- Concepts should take 30-60 minutes total (reading + tasks)
- Order them from foundational to advanced
- Keep titles clear and concise (3-6 words)

**Return ONLY valid JSON array:**
[
  {{
    "order_index": 1,
    "title": "Concept Title (3-6 words)",
    "description": "Brief 1-sentence description"
  }},
  ...
]

**CRITICAL:** 
- Return ONLY the JSON array, no markdown formatting
- Include 3-5 concepts
"""
