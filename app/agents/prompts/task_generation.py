"""
Task generation prompt template.
Generates task descriptions and test files in a single LLM call.

Uses NOTEBOOK REPO (user_repo_url) context, not textbook repo.
Generates language-appropriate tests (pytest for Python, jest for JavaScript).
"""

TASK_GENERATION_PROMPT = """You are a technical educator creating verifiable coding tasks.

**Context:**
- Concept: {concept_title}
- Concept Objective: {concept_objective}
- Skill Level: {skill_level}
- **PROJECT LANGUAGE: {project_language}** ⚠️ CRITICAL - ALL tests MUST match this language
- Notebook Repository Structure: {notebook_repo_structure}
- Notebook Repository Code Context: {notebook_repo_code_context}
- Existing Test Structure: {existing_test_structure}

**Previous Learning Context:**
{memory_context}

**🚨 MANDATORY LANGUAGE RULES - READ CAREFULLY:**

The PROJECT LANGUAGE above is: **{project_language}**

**IF project_language is "javascript" or "typescript":**
  ✅ REQUIRED: test_file_path MUST end with .test.js or .test.ts
  ✅ REQUIRED: test_command MUST start with "npx jest" or "npm test"
  ✅ REQUIRED: test_file_content MUST use Jest syntax (describe, test, expect)
  ❌ FORBIDDEN: Do NOT use .py extension
  ❌ FORBIDDEN: Do NOT use pytest command
  ❌ FORBIDDEN: Do NOT use Python syntax (import pytest, def test_)

**IF project_language is "python":**
  ✅ REQUIRED: test_file_path MUST end with .py (e.g., test_task_1.py)
  ✅ REQUIRED: test_command MUST start with "pytest"
  ✅ REQUIRED: test_file_content MUST use pytest syntax (import pytest, def test_)
  ❌ FORBIDDEN: Do NOT use .test.js extension
  ❌ FORBIDDEN: Do NOT use jest command
  ❌ FORBIDDEN: Do NOT use JavaScript syntax (describe, test, expect)

**VERIFICATION CHECKLIST BEFORE RETURNING:**
1. Check test_file_path extension matches project_language
2. Check test_command matches project_language framework
3. Check test_file_content syntax matches project_language
4. If ANY mismatch, regenerate the task

**Your Task:**
Generate 2-4 coding tasks with executable test files matching the project language.

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

**Test File Examples by Language:**

**EXAMPLE FOR JAVASCRIPT PROJECTS (project_language = "javascript"):**
{{
  "order_index": 1,
  "title": "Create Express Route",
  "description": "Create a GET route at /api/hello that returns {{'message': 'Hello World'}}",
  "task_type": "coding",
  "estimated_minutes": 15,
  "difficulty": "easy",
  "test_file_path": "tests/task_1.test.js",
  "test_file_content": "const request = require('supertest');\\nconst app = require('../server');\\n\\ndescribe('GET /api/hello', () => {{\\n  test('should return Hello World message', async () => {{\\n    const res = await request(app).get('/api/hello');\\n    expect(res.statusCode).toBe(200);\\n    expect(res.body).toEqual({{ message: 'Hello World' }});\\n  }});\\n}});",
  "test_command": "npx jest tests/task_1.test.js"
}}

**EXAMPLE FOR PYTHON PROJECTS (project_language = "python"):**
{{
  "order_index": 1,
  "title": "Create Flask Route",
  "description": "Create a GET route at /api/hello that returns {{'message': 'Hello World'}}",
  "task_type": "coding",
  "estimated_minutes": 15,
  "difficulty": "easy",
  "test_file_path": "tests/test_task_1.py",
  "test_file_content": "import pytest\\nfrom app import app\\n\\ndef test_hello_route(client):\\n    response = client.get('/api/hello')\\n    assert response.status_code == 200\\n    assert response.json == {{'message': 'Hello World'}}",
  "test_command": "pytest tests/test_task_1.py -v"
}}

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
      "test_file_path": "tests/task_1.test.js",
      "test_file_content": "// Test content matching project language - MUST use correct syntax",
      "test_command": "npx jest tests/task_1.test.js"
    }}
  ]
}}

**CRITICAL JSON FORMATTING:**
- Return ONLY a JSON object, no text before or after
- Escape ALL newlines as \\n
- Escape ALL quotes inside strings as \\"
- Escape backslashes as \\\\
- test_file_path MUST match project language (.test.js/.test.ts for JS, .py for Python)
- test_command MUST match project language (npx jest/npm test for JS, pytest for Python)
- test_file_content MUST use correct syntax (Jest for JS, pytest for Python)
- task_type must be "coding"
- difficulty must be "easy", "medium", or "hard"

**FINAL CHECK:**
Before returning, verify that for project_language="{project_language}":
- test_file_path extension is correct
- test_command framework is correct
- test_file_content syntax is correct
"""
