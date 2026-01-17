"""
Repository analysis prompt template.
Analyzes GitHub repositories to extract technology stack and architecture.

Uses two-stage analysis to handle large codebases:
1. First stage: High-level overview with subset of chunks
2. Second stage: Detailed analysis with summary + remaining chunks
"""

# DEPRECATED: Use REPO_ANALYSIS_STAGE1_PROMPT and REPO_ANALYSIS_STAGE2_PROMPT instead
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

REPO_ANALYSIS_STAGE1_PROMPT = """You are an expert software engineer analyzing a GitHub repository to create a learning curriculum.

**Repository Information:**
- URL: {github_url}
- Skill Level: {skill_level}
- Target Days: {target_days}

**Code Context from Repository (Sample):**
{code_context}

**Your Task:**
Analyze this sample of code from the repository and provide a HIGH-LEVEL overview.

Focus on:
1. What technologies are used (languages, frameworks, libraries)
2. The project's general architecture pattern
3. What this project appears to do (high-level functionality)

**Return ONLY valid JSON in this exact format:**
{{
  "summary": "2-3 sentence overview of what this project does based on the code sample",
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
- This is a preliminary analysis - be concise
"""

REPO_ANALYSIS_STAGE2_PROMPT = """You are an expert software engineer analyzing a GitHub repository to create a learning curriculum.

**Repository Information:**
- URL: {github_url}
- Skill Level: {skill_level}
- Target Days: {target_days}

**Preliminary Analysis (from first pass):**
{preliminary_analysis}

**Additional Code Context from Repository:**
{code_context}

**Your Task:**
Refine and complete the analysis using the preliminary findings and additional code context.

Provide a comprehensive assessment for curriculum design:
1. Refine the summary with more detail
2. Complete the list of technologies (languages, frameworks, libraries)
3. Identify all architecture patterns and design patterns used
4. Assess the difficulty level accurately
5. Note key features and functionality

**Return ONLY valid JSON in this exact format:**
{{
  "summary": "2-3 sentence comprehensive overview of what this project does and why it's good for learning",
  "primary_language": "Python/JavaScript/etc",
  "frameworks": ["framework1", "framework2", "framework3"],
  "architecture_patterns": ["MVC", "REST API", "Microservices", "Layered", "etc"],
  "difficulty": "beginner/intermediate/advanced"
}}

**CRITICAL:**
- Return ONLY the JSON object
- NO markdown code blocks (no ```json or ```)
- NO explanatory text before or after
- Start with {{ and end with }}
- Build upon the preliminary analysis but refine with additional context
"""
