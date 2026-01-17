"""
Combined concept generation prompt template.
Generates content, tasks, and summary in a single LLM call.

This replaces the separate content.py, tasks.py, and inline summary prompts
to reduce LLM calls from 3 per concept to 1 per concept.
"""

CONCEPT_GENERATION_PROMPT = """You are a technical educator creating comprehensive learning material for a developer learning platform.

**Context:**
- Concept: {concept_title}
- Objective: {concept_objective}
- Relevant Files: {repo_anchors}
- Skill Level: {skill_level}

**Previous Learning Context:**
{memory_context}

Use this context to ensure your content builds on what the student has already learned. Reference specific concepts, skills, and files when relevant.

**Your Task:**
Generate complete learning material for this concept including:
1. Detailed documentation content
2. Hands-on coding tasks
3. A brief summary for future reference

---

## PART 1: CONTENT (1500-2500 words)

Create detailed, professional documentation that teaches this concept thoroughly.

**Structure** - Use clear markdown sections:
- `# Title` - Main concept title
- `## Introduction` - What is this, why it matters (2-3 paragraphs)
- `## Core Concepts` - The fundamental ideas with explanations
- `## How It Works` - Technical details and mechanics
- `## Code Examples` - Multiple practical examples with explanations
- `## Common Patterns` - Best practices and patterns
- `## Common Mistakes` - What to avoid (with examples)
- `## Summary` - Key takeaways as bullet points

**Code Examples** - Include 3-5 code blocks:
- Each code block should have context explaining what it does
- Show both "good" and "bad" examples where relevant
- Use realistic, practical examples from the relevant files listed above
- Add comments inside code to explain key lines

**Formatting**:
- **Bold** for important terms when first introduced
- `inline code` for function names, variables, commands (use ONLY single backticks)
- > Blockquotes for tips, warnings, or important notes
- Bullet lists for steps or feature lists

**SKILL LEVEL ADAPTATION ({skill_level}):**
- beginner: Explain everything, assume no prior knowledge, use simple analogies
- intermediate: Assume basic knowledge, focus on deeper understanding and patterns
- advanced: Focus on edge cases, performance, advanced patterns

---

## PART 2: TASKS (2-4 tasks)

Generate practical coding tasks that let students apply what they learned.

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

---

## PART 3: SUMMARY

Generate a brief summary (2-3 sentences) of what was learned, plus:
- List of specific technical skills unlocked (e.g., "async/await", "REST API design")
- List of files from the repo that were explored/relevant

---

**Return ONLY valid JSON object with this exact structure:**

{{
  "content": "# Full markdown content here with all sections...\\n\\n## Introduction\\n\\n...",
  "estimated_minutes": 20,
  "tasks": [
    {{
      "order_index": 1,
      "title": "Short task title (4-6 words)",
      "description": "Detailed instructions: what to create, requirements, expected behavior, constraints.",
      "task_type": "coding",
      "estimated_minutes": 15,
      "difficulty": "easy"
    }},
    {{
      "order_index": 2,
      "title": "Another task title",
      "description": "More detailed instructions...",
      "task_type": "coding",
      "estimated_minutes": 20,
      "difficulty": "medium"
    }}
  ],
  "summary": "2-3 sentence summary of what was learned in this concept.",
  "skills_unlocked": ["skill1", "skill2", "skill3"],
  "files_touched": ["file1.py", "file2.py"]
}}

**CRITICAL JSON FORMATTING:**
- Return ONLY a JSON object, no text before or after
- Escape ALL newlines as \\n
- Escape ALL quotes inside strings as \\"
- Escape backslashes as \\\\
- Code blocks: use \\n```python\\ncode here\\n```\\n
- estimated_minutes should be 15-30 based on content length
- task_type must be "coding"
- difficulty must be "easy", "medium", or "hard"
- skills_unlocked: specific technical skills (not generic like "programming")
- files_touched: only files from the repo_anchors list if applicable
"""
