"""
Pattern extraction prompt template.
Extracts verification patterns from test files using LLM.

Small, focused LLM call - much cheaper than task generation.
"""

PATTERN_EXTRACTION_PROMPT = """You are analyzing a test file to extract verification patterns.

**Test File:**
```{language}
{test_file_content}
```

**Your Task:**
Analyze this test file and extract verification patterns that indicate what the student's code must implement.

**Extract:**
1. **Required Functions**: Functions that must exist (name, params, return type if inferable)
2. **Required Classes**: Classes that must exist (name, methods if inferable)
3. **Required Imports**: Modules/packages that must be imported
4. **Code Patterns**: Specific patterns that should exist (e.g., uses async/await, uses list comprehension)
5. **Forbidden Patterns**: Patterns that should NOT exist (if test explicitly avoids them)

**Guidelines:**
- Only extract what the test file explicitly checks
- Don't infer requirements that aren't tested
- Be specific about function signatures based on test calls
- Extract patterns that help verify code structure before running tests

**Return ONLY valid JSON:**
{{
  "required_functions": [
    {{
      "name": "function_name",
      "params": ["param1", "param2"],
      "return_type": "int"
    }}
  ],
  "required_classes": [
    {{
      "name": "ClassName",
      "methods": ["method1", "method2"]
    }}
  ],
  "required_imports": ["module1", "module2"],
  "code_patterns": [
    {{
      "type": "uses_builtin",
      "pattern": "sum",
      "description": "Must use built-in sum() function"
    }},
    {{
      "type": "uses_feature",
      "pattern": "async/await",
      "description": "Must use async/await"
    }}
  ],
  "forbidden_patterns": [
    {{
      "type": "regex",
      "pattern": "for.*in.*:",
      "description": "Should not use explicit loops"
    }}
  ]
}}
"""
