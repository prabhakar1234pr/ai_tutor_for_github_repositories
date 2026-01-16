"""
Task generation prompt template.
Generates coding tasks with verification criteria.
"""

TASKS_GENERATION_PROMPT = """You are creating hands-on coding tasks for a learning platform.

**Context:**
- Day Number: {day_number}
- Concept: {concept_title}
- Description: {concept_description}
- Skill Level: {skill_level}

**Your Task:**
Generate 2-4 practical coding tasks that let students apply what they learned.

 **TASK REQUIREMENTS:**

 1. **Progressive Difficulty**:
   - First task: "easy" - Basic application of the concept
   - Middle tasks: "medium" - Combining concepts or adding complexity
   - Last task: "hard" (optional) - Challenge task for advanced learners

2. **Clear Instructions**: Each task description should include:
   - What to build/create
   - Specific requirements (inputs, outputs, features)
   - Expected behavior or result
    - Any constraints or guidelines

 3. **Practical & Realistic**:
   - Tasks should build toward real project features
   - Use realistic scenarios (not abstract puzzles)
   - Connect to the project they're learning to build

4. **Time Estimates**:
   - easy: 10-15 minutes
   - medium: 15-25 minutes
   - hard: 25-40 minutes

**SKILL LEVEL ADAPTATION ({skill_level}):**
- beginner: More guidance, simpler requirements, focus on one concept at a time
- intermediate: Less hand-holding, combine multiple concepts, expect problem-solving
- advanced: Minimal guidance, complex requirements, edge cases, optimization

**Example Tasks:**

```json
[
  {{
    "order_index": 1,
    "title": "Create User Variables",
    "description": "Create a Python file called user_profile.py. Define variables to store: user's name (string), age (integer), email (string), and is_premium_member (boolean). Print each variable with a descriptive label. Example output: 'Name: Alice'",
    "task_type": "coding",
    "estimated_minutes": 10,
    "difficulty": "easy"
  }},
  {{
    "order_index": 2,
    "title": "Build a User Summary Function",
    "description": "Create a function called get_user_summary() that takes name, age, and is_premium as parameters. Return a formatted string like: 'Alice (25) - Premium Member' or 'Bob (30) - Free User'. Handle edge cases: empty name should return 'Anonymous'.",
    "task_type": "coding",
    "estimated_minutes": 20,
    "difficulty": "medium"
  }}
]
```

**Return ONLY valid JSON array:**
[
  {{
    "order_index": 1,
    "title": "Short task title (4-6 words)",
    "description": "Detailed instructions: what to create, requirements, expected behavior, constraints. Be specific!",
    "task_type": "coding",
    "estimated_minutes": 15,
    "difficulty": "easy"
  }},
  ...
]

**CRITICAL JSON FORMATTING:**
- Return ONLY a JSON array, no text before or after
- task_type must be "coding"
- difficulty must be "easy", "medium", or "hard"
- estimated_minutes: 10-40 based on difficulty
- Escape quotes and special characters properly
"""
