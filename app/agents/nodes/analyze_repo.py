"""
Analyze repository using RAG to understand its structure and technologies.
This node uses Qdrant embeddings to retrieve relevant code context.
"""

import logging
from app.agents.state import RoadmapAgentState, RepoAnalysis
from app.services.rag_pipeline import generate_rag_response
from app.services.groq_service import get_groq_service
from app.agents.prompts import REPO_ANALYSIS_PROMPT
from app.utils.json_parser import parse_llm_json_response_async

logger = logging.getLogger(__name__)


async def analyze_repository(state: RoadmapAgentState) -> RoadmapAgentState:
    """
    Analyze the GitHub repository using RAG to understand its structure.
    
    This node:
    1. Uses RAG to retrieve relevant code chunks from the repository
    2. Calls Groq LLM to analyze the repository structure
    3. Parses the JSON response into RepoAnalysis
    4. Updates state with the analysis
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with repo_analysis populated
    """
    project_id = state["project_id"]
    github_url = state["github_url"]
    skill_level = state["skill_level"]
    target_days = state["target_days"]
    
    logger.info(f"🔍 Analyzing repository: {github_url}")
    
    # Step 1: Use RAG to get repository context
    logger.info("📚 Retrieving repository context using RAG...")
    
    # Query RAG for repository overview
    rag_query = (
        "What is this project about? What technologies, frameworks, and patterns does it use? "
        "What is the overall architecture and structure?"
    )
    
    try:
        rag_result = await generate_rag_response(
            project_id=project_id,
            query=rag_query,
            top_k=10,  # Get more chunks for better context
        )
        
        code_context = rag_result["response"]
        chunks_used = rag_result.get("chunks_used", [])
        
        logger.info(f"✅ Retrieved {len(chunks_used)} code chunks for analysis")
        logger.debug(f"   Context length: {len(code_context)} chars")
        
    except Exception as e:
        logger.warning(f"⚠️  RAG retrieval failed: {e}. Using empty context.")
        code_context = "No code context available."
    
    # Step 2: Call Groq LLM to analyze the repository
    logger.info("🤖 Analyzing repository structure with LLM...")
    
    groq_service = get_groq_service()
    
    # Format the prompt
    prompt = REPO_ANALYSIS_PROMPT.format(
        github_url=github_url,
        skill_level=skill_level,
        target_days=target_days,
        code_context=code_context,
    )
    
    # Call LLM
    system_prompt = (
        "You are an expert software engineer analyzing codebases. "
        "CRITICAL: Return ONLY valid JSON. Do NOT use markdown code blocks. "
        "Do NOT add any text before or after the JSON. Start with { and end with }."
    )
    
    try:
        # Use async version with rate limiting
        llm_response = await groq_service.generate_response_async(
            user_query=prompt,
            system_prompt=system_prompt,
            context="",  # Context already in prompt
        )
        
        logger.debug(f"   LLM response length: {len(llm_response)} chars")
        logger.debug(f"   Raw LLM response: {llm_response[:200]}...")
        
        # Step 3: Parse JSON response using async parser (supports sanitizer)
        try:
            analysis_dict = await parse_llm_json_response_async(llm_response, expected_type="object")
        except Exception as parse_error:
            logger.error(f"❌ Failed to parse JSON response: {parse_error}")
            logger.error(f"   Original response: {llm_response[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {parse_error}")
        
        # Step 4: Create RepoAnalysis object
        repo_analysis: RepoAnalysis = {
            "summary": analysis_dict.get("summary", ""),
            "primary_language": analysis_dict.get("primary_language", ""),
            "frameworks": analysis_dict.get("frameworks", []),
            "architecture_patterns": analysis_dict.get("architecture_patterns", []),
            "difficulty": analysis_dict.get("difficulty", "intermediate"),
        }
        
        logger.info(f"✅ Repository analysis complete:")
        logger.info(f"   Primary Language: {repo_analysis['primary_language']}")
        logger.info(f"   Frameworks: {', '.join(repo_analysis['frameworks'])}")
        logger.info(f"   Architecture: {', '.join(repo_analysis['architecture_patterns'])}")
        logger.info(f"   Difficulty: {repo_analysis['difficulty']}")
        
        # Update state
        state["repo_analysis"] = repo_analysis
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Repository analysis failed: {e}", exc_info=True)
        # Set error in state
        state["error"] = f"Repository analysis failed: {str(e)}"
        return state

