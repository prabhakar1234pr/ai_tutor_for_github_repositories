"""
Content generation prompt template.
Generates comprehensive markdown documentation for learning concepts.
"""

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
