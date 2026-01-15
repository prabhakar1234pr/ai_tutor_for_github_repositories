"""
Repository analysis prompt template.
Analyzes GitHub repositories to extract technology stack and architecture.
"""

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
