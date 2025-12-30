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
- NO comments
- Start with {{ and end with }}
- Example of correct response:
{{"summary": "...", "primary_language": "...", "frameworks": [...], "architecture_patterns": [...], "difficulty": "..."}}
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
- Each day's theme must be clearly distinct from previous days (no repetition or rewording)
- Match the {skill_level} skill level
- Each day should take 2-4 hours to complete

**Example Progression for a Web App:**
- Day 1: HTML/CSS Basics & Project Structure
- Day 2: JavaScript Fundamentals & DOM Manipulation
- Day 3: Event Handling & User Interactions
- Day 4: API Integration & Async JavaScript
- ... and so on (each day clearly different)

**Return ONLY valid JSON array starting from day 1:**
[
  {{
    "day_number": 1,
    "theme": "Short descriptive theme (5-8 words)",
    "description": "1-2 sentences explaining what the student will learn and build this day"
  }},
  {{
    "day_number": 2,
    "theme": "...",
    "description": "..."
  }},
  ...
  {{
    "day_number": {last_day_number},
    "theme": "...",
    "description": "..."
  }}
]

**CRITICAL:** 
- Return ONLY the JSON array, no markdown formatting, no extra text
- Start from day 1 (Day 0 is handled separately)
- Include exactly {last_day_number} days
- Each theme must be unique and clearly distinct
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
Generate 3-5 major learning concepts for this day. Each concept is a big topic the student will learn.

**Guidelines:**
- Each concept should be a substantial topic (e.g., "Variables and Data Types", "Functions and Scope", "API Integration")
- Concepts must directly support the day's theme and be necessary to understand or build the project
- Concepts should take 30-60 minutes each to complete
- They should build toward understanding the project
- Order them from foundational to advanced within the day
- Keep titles clear and concise (3-6 words)

**Example concepts for "Day 1: Python Basics":**
1. "Variables and Data Types" - Understanding how to store data
2. "Control Flow and Conditionals" - Making decisions in code
3. "Lists and Loops" - Working with collections

**Return ONLY valid JSON array:**
[
  {{
    "order_index": 1,
    "title": "Concept Title (3-6 words)",
    "description": "Brief 1-sentence description of what student will learn"
  }},
  {{
    "order_index": 2,
    "title": "...",
    "description": "..."
  }},
  ...
]

**CRITICAL:** 
- Return ONLY the JSON array, no markdown formatting
- Include 3-5 concepts
- Keep descriptions concise (one sentence)
- Concepts must be relevant to the day's theme
"""

# ===== SUBCONCEPTS GENERATION PROMPT =====
SUBCONCEPTS_GENERATION_PROMPT = """You are creating educational content for a specific learning concept.

**Context:**
- Day Number: {day_number}
- Concept: {concept_title}
- Description: {concept_description}
- Skill Level: {skill_level}

**Your Task:**
Generate 2-4 subconcepts with detailed markdown content. Each subconcept explains a specific aspect of the main concept.

**Guidelines:**
- Each subconcept should cover one specific sub-topic
- Content should be educational, clear, and example-rich
- Use markdown formatting (headers, code blocks, lists, bold)
- Include code examples where relevant
- Keep each subconcept 150-300 words
- Write for {skill_level} level

**Example for concept "Variables and Data Types":**
1. "What are Variables?" - Explain variables as containers
2. "Common Data Types" - Strings, numbers, booleans with examples
3. "Variable Naming Rules" - Best practices and conventions

**Content Format Example:**
```markdown
# What are Variables?

Variables are containers that store data values. Think of them as labeled boxes where you can put information and retrieve it later.

**Key Points:**
- Variables have names and values
- You can change a variable's value
- Use descriptive names for clarity

**Example:**
\`\`\`python
name = "Alice"
age = 25
is_student = True
\`\`\`

In this example, we store a person's information in three variables.
```

**Return ONLY valid JSON array:**
[
  {{
    "order_index": 1,
    "title": "Subconcept Title (3-5 words)",
    "content": "# Title\\n\\nFull markdown content here with examples..."
  }},
  {{
    "order_index": 2,
    "title": "...",
    "content": "..."
  }},
  ...
]

**CRITICAL:** 
- Return ONLY the JSON array
- Include 2-4 subconcepts
- Content must be in markdown format
- Escape quotes properly in JSON
- Do NOT include unescaped newline characters inside JSON strings
- Include code examples where relevant
"""

# ===== TASKS GENERATION PROMPT =====
TASKS_GENERATION_PROMPT = """You are creating coding tasks for students to practice what they learned.

**Context:**
- Day Number: {day_number}
- Concept: {concept_title}
- Description: {concept_description}
- Skill Level: {skill_level}

**Your Task:**
Generate 3-5 hands-on coding tasks that let students apply this concept.

**Guidelines:**
- Each task should be specific and actionable
- Tasks should increase in difficulty
- Provide clear instructions on what to code
- Tasks should build toward the final project
- Match the {skill_level} level
- All tasks should have task_type: "coding" (unless it's Day 0)

**Example tasks for "Variables and Data Types":**
1. "Create variables for user profile" - Store name, age, email in variables
2. "Calculate and store results" - Use variables for math operations
3. "Variable reassignment practice" - Update variable values and print results

**Return ONLY valid JSON array:**
[
  {{
    "order_index": 1,
    "title": "Short task title (4-6 words)",
    "description": "Clear instructions: What to create, what functionality to implement, what the output should be. Be specific about requirements.",
    "task_type": "coding"
  }},
  {{
    "order_index": 2,
    "title": "...",
    "description": "...",
    "task_type": "coding"
  }},
  ...
]

**CRITICAL:** 
- Return ONLY the JSON array
- Include 3-5 tasks
- task_type is always "coding" for regular days
- Descriptions should be clear and specific
- Order tasks from easiest to hardest
"""