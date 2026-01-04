"""
LLM prompts for roadmap generation agent.
All prompts are designed to return structured JSON for parsing.
"""

# ===== REPOSITORY ANALYSIS PROMPT =====
REPO_ANALYSIS_PROMPT = """You are an expert software engineer analyzing a GitHub repository to create a learning curriculum.

**Repository Information:**
- URL: {github_url}
- Skill Level: {skill_level}
- Target Days: {target_days}

**Code Context from Repository:**
{code_context}

**Your Task:**
Analyze this repository and provide a structured assessment for curriculum design.

Focus on:
1. What technologies are used (languages, frameworks, libraries)
2. The project's architecture and design patterns
3. Key features and functionality
4. What makes this project a good learning opportunity
5. What order topics should be taught (fundamentals first)

**Return ONLY valid JSON in this exact format:**
{{
  "summary": "2-3 sentence overview of what this project does and why it's good for learning",
  "primary_language": "Python/JavaScript/etc",
  "frameworks": ["framework1", "framework2"],
  "architecture_patterns": ["MVC", "REST API", "Microservices", "Layered", "etc"],
  "difficulty": "beginner/intermediate/advanced"
}}

**CRITICAL:** 
- Return ONLY the JSON object
- NO markdown code blocks (no ```json or ```)
- NO explanatory text before or after
- Start with {{ and end with }}
"""

# ===== CURRICULUM PLANNING PROMPT =====
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

# ===== CONCEPTS GENERATION PROMPT =====
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

# ===== CONTENT GENERATION PROMPT =====
CONTENT_GENERATION_PROMPT = """You are a technical writer creating comprehensive documentation for a learning platform.

**Context:**
- Day Number: {day_number}
- Concept: {concept_title}
- Description: {concept_description}
- Skill Level: {skill_level}

**Your Task:**
Create detailed, professional documentation that teaches this concept thoroughly. This will be displayed as a full-page reading experience, so make it comprehensive and engaging.

**CONTENT REQUIREMENTS:**

1. **Length**: 1500-2500 words (this is a full documentation page, not a summary)

2. **Structure** - Use clear markdown sections:
   - `# Title` - Main concept title
   - `## Introduction` - What is this, why it matters (2-3 paragraphs)
   - `## Core Concepts` - The fundamental ideas with explanations
   - `## How It Works` - Technical details and mechanics
   - `## Code Examples` - Multiple practical examples with explanations
   - `## Common Patterns` - Best practices and patterns
   - `## Common Mistakes` - What to avoid (with examples)
   - `## Summary` - Key takeaways as bullet points

3. **Code Examples** - Include 3-5 code blocks:
   - Each code block should have context explaining what it does
   - Show both "good" and "bad" examples where relevant
   - Use realistic, practical examples
   - Add comments inside code to explain key lines

4. **Formatting** - Use rich markdown:
   - **Bold** for important terms when first introduced
   - `inline code` for function names, variables, commands (use ONLY single backticks like `name`, NEVER multiple backticks)
   - > Blockquotes for tips, warnings, or important notes
   - Bullet lists for steps or feature lists
   - Numbered lists for sequential processes

**CRITICAL INLINE CODE FORMATTING:**
- For inline code, use EXACTLY ONE backtick on each side: `example`
- NEVER use multiple backticks like ``example`` or ```example```
- Multiple backticks are ONLY for code blocks (on their own line with language specifier)

5. **Writing Style**:
   - Write like MDN Web Docs or official documentation
   - Be clear and precise, avoid fluff
   - Explain the "why" not just the "how"
   - Use analogies for complex concepts ({skill_level} level)
   - Include practical real-world applications

**SKILL LEVEL ADAPTATION ({skill_level}):**
- beginner: Explain everything, assume no prior knowledge, use simple analogies
- intermediate: Assume basic knowledge, focus on deeper understanding and patterns
- advanced: Focus on edge cases, performance, advanced patterns, less hand-holding

**Example Structure:**

```
# Variables and Data Types

## Introduction

Variables are fundamental building blocks in programming...

> 💡 **Key Insight**: Think of variables as labeled containers...

## Core Concepts

### What is a Variable?

A **variable** is a named storage location...

### Data Types

Python has several built-in data types:
- **Strings** - Text data like `"Hello"`
- **Integers** - Whole numbers like `42`
...

## Code Examples

### Basic Variable Declaration

```python
# Declaring variables
name = "Alice"
age = 25
is_student = True
```

In this example, we create three variables...

## Common Mistakes

### Mistake 1: Using undeclared variables
...

## Summary

- Variables store data with meaningful names
- Python has dynamic typing
...
```

**Return ONLY valid JSON object:**
{{
  "content": "# Full markdown content here with all sections...\\n\\n## Introduction\\n\\n...",
  "estimated_minutes": 20
}}

**CRITICAL JSON FORMATTING:**
- Return ONLY a JSON object, no text before or after
- Escape ALL newlines as \\n
- Escape ALL quotes inside strings as \\"
- Escape backslashes as \\\\
- Code blocks: use \\n```python\\ncode here\\n```\\n
- estimated_minutes should be 15-30 based on content length
- Content must be valid JSON string (test with JSON.parse)
- INLINE CODE: Use SINGLE backticks only (`word`), never multiple backticks for inline code
"""

# ===== TASKS GENERATION PROMPT =====
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
