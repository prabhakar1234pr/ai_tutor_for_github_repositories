"""
Task generation prompt template.
Generates task descriptions and test files in a single LLM call.

Uses NOTEBOOK REPO (user_repo_url) context, not textbook repo.
"""

TASK_GENERATION_PROMPT = """You are a technical educator creating verifiable coding tasks.

**Context:**
- Concept: {concept_title}
- Concept Objective: {concept_objective}
- Skill Level: {skill_level}
- Notebook Repository Structure: {notebook_repo_structure}
- Notebook Repository Code Context: {notebook_repo_code_context}
- Existing Test Structure: {existing_test_structure}

**Previous Learning Context:**
{memory_context}

**Important:**
- Generate tasks that match the NOTEBOOK repository structure (where user is building)
- Test files must be executable in the user's actual project
- Use the actual file paths and structure from notebook repo
- If notebook repo is new/empty, create appropriate structure
- Follow existing test framework conventions if detected

**Your Task:**
Generate 2-4 coding tasks with executable test files.

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

**Test File Requirements:**
1. Test file path must match notebook repository structure
2. Use appropriate testing framework (based on existing_test_structure)
3. Test file must be self-contained and executable
4. Test command must be specific (e.g., "pytest tests/test_task_1.py -v")
5. Tests should verify both correctness and edge cases

**Test Framework Guidelines:**
- If framework is "pytest": Use pytest syntax, place in tests/ directory, use test_*.py naming
- If framework is "jest": Use Jest syntax, place in __tests__/ or tests/, use *.test.js naming
- If framework is "none": Infer from repository language (pytest for Python, jest for JavaScript)
- Follow existing test patterns if examples are provided

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
      "test_file_path": "tests/test_task_1.py",
      "test_file_content": "import pytest\\n\\ndef test_task_1():\\n    # Test implementation\\n    assert True",
      "test_command": "pytest tests/test_task_1.py -v"
    }},
    {{
      "order_index": 2,
      "title": "Another task title",
      "description": "More detailed instructions...",
      "task_type": "coding",
      "estimated_minutes": 20,
      "difficulty": "medium",
      "test_file_path": "tests/test_task_2.py",
      "test_file_content": "import pytest\\n\\ndef test_task_2():\\n    # Test implementation\\n    assert True",
      "test_command": "pytest tests/test_task_2.py -v"
    }}
  ]
}}

**CRITICAL JSON FORMATTING:**
- Return ONLY a JSON object, no text before or after
- Escape ALL newlines as \\n
- Escape ALL quotes inside strings as \\"
- Escape backslashes as \\\\
- test_file_path must match notebook repo structure
- test_command must be executable in the user's environment
- task_type must be "coding"
- difficulty must be "easy", "medium", or "hard"
"""
