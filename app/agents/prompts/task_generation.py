"""
Task generation prompt template.
Generates task descriptions only (no tests).

Uses NOTEBOOK REPO (user_repo_url) context, not textbook repo.
"""

TASK_GENERATION_PROMPT = """You are a technical educator creating coding tasks.

**Context:**
- Concept: {concept_title}
- Concept Objective: {concept_objective}
- Skill Level: {skill_level}
- Project Language: {project_language}
- Notebook Repository Structure: {notebook_repo_structure}
- Notebook Repository Code Context: {notebook_repo_code_context}

**Previous Learning Context:**
{memory_context}

**Your Task:**
Generate 2-4 coding tasks (descriptions only). Do NOT generate tests. Do NOT include test files or test commands.

**Task Requirements:**
1. **Progressive Difficulty**:
   - First task: "easy" - Basic application of the concept
   - Middle tasks: "medium" - Combining concepts or adding complexity
   - Last task: "hard" (optional) - Challenge task for advanced learners

2. **Clear Instructions**: Each task description should include:
   - What to build/create
   - Specific requirements (inputs, outputs, features)
   - Expected behavior or result
   - Any constraints or guidelines

3. **Time Estimates**:
   - easy: 10-15 minutes
   - medium: 15-25 minutes
   - hard: 25-40 minutes

**Return ONLY valid JSON object with this exact structure:**

{{
  "tasks": [
    {{
      "order_index": 1,
      "title": "Short task title (4-6 words)",
      "description": "Detailed instructions: what to create, requirements, expected behavior, constraints.",
      "task_type": "coding",
      "estimated_minutes": 15,
      "difficulty": "easy",
      "hints": ["Optional hint 1", "Optional hint 2"]
    }}
  ]
}}

**CRITICAL JSON FORMATTING:**
- Return ONLY a JSON object, no text before or after
- Escape ALL newlines as \\n
- Escape ALL quotes inside strings as \\"
- Escape backslashes as \\\\
- task_type must be "coding"
- difficulty must be "easy", "medium", or "hard"
"""
