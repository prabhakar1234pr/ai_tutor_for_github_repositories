"""
Analyze repository using RAG to understand its structure and technologies.
This node uses Qdrant embeddings to retrieve relevant code context.

Optimized with adaptive token budgeting to prevent token limit errors:
- Retrieves more chunks initially (top_k=15)
- Truncates each chunk to MAX_CHUNK_TOKENS (500)
- Selects chunks within ANALYZE_REPO_TOKEN_BUDGET (6000)
"""

import logging

from app.agents.prompts import REPO_ANALYSIS_PROMPT
from app.agents.state import RepoAnalysis, RoadmapAgentState
from app.core.supabase_client import get_supabase_client
from app.services.embedding_service import get_embedding_service
from app.services.groq_service import get_groq_service
from app.services.qdrant_service import get_qdrant_service
from app.utils.json_parser import parse_llm_json_response_async
from app.utils.token_budgeting import (
    ANALYZE_REPO_TOKEN_BUDGET,
    MAX_CHUNK_TOKENS,
    build_context_from_chunks,
    select_chunks_by_budget,
)

logger = logging.getLogger(__name__)

# Retrieve more chunks than needed, then filter with token budget
INITIAL_TOP_K = 15


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

    # Step 1: Retrieve code chunks with adaptive token budgeting
    logger.info("📚 Retrieving repository context with token budgeting...")
    logger.debug(f"   Token budget: {ANALYZE_REPO_TOKEN_BUDGET}, Max per chunk: {MAX_CHUNK_TOKENS}")

    # Query for repository overview
    rag_query = (
        "What is this project about? What technologies, frameworks, and patterns does it use? "
        "What is the overall architecture and structure?"
    )

    try:
        # Step 1a: Generate embedding for query
        embedding_service = get_embedding_service()
        query_embeddings = embedding_service.embed_texts([rag_query])

        if not query_embeddings or len(query_embeddings) == 0:
            raise ValueError("Failed to generate embedding for query")

        query_embedding = query_embeddings[0]

        # Step 1b: Search Qdrant for similar chunks (retrieve more than needed)
        qdrant_service = get_qdrant_service()
        search_results = qdrant_service.search(
            project_id=project_id,
            query_embedding=query_embedding,
            limit=INITIAL_TOP_K,  # Retrieve more chunks initially
        )

        if not search_results:
            raise ValueError(f"No chunks found for project {project_id}")

        logger.info(f"   Retrieved {len(search_results)} chunks from Qdrant (initial)")

        # Step 1c: Get chunk content from Supabase
        chunk_ids = [str(result.id) for result in search_results]
        chunk_scores = {str(result.id): result.score for result in search_results}

        supabase = get_supabase_client()
        chunks_response = (
            supabase.table("project_chunks")
            .select("id, file_path, chunk_index, language, content, token_count")
            .in_("id", chunk_ids)
            .execute()
        )

        if not chunks_response.data:
            raise ValueError("Chunks not found in Supabase")

        # Step 1d: Build chunk list with all metadata
        raw_chunks = []
        for chunk_id in chunk_ids:  # Maintain order from Qdrant (by similarity)
            chunk_data = next((c for c in chunks_response.data if str(c["id"]) == chunk_id), None)
            if chunk_data:
                raw_chunks.append(
                    {
                        "id": chunk_id,
                        "file_path": chunk_data["file_path"],
                        "chunk_index": chunk_data["chunk_index"],
                        "language": chunk_data["language"],
                        "content": chunk_data["content"],
                        "token_count": chunk_data["token_count"],
                        "score": chunk_scores.get(chunk_id, 0.0),
                    }
                )

        # Step 1e: Apply token budgeting - select and truncate chunks
        selected_chunks = select_chunks_by_budget(
            chunks=raw_chunks,
            token_budget=ANALYZE_REPO_TOKEN_BUDGET,
            max_chunk_tokens=MAX_CHUNK_TOKENS,
        )

        # Step 1f: Build context string from selected chunks
        code_context = build_context_from_chunks(selected_chunks)

        # Log stats
        total_original_tokens = sum(c.get("original_token_count", 0) for c in selected_chunks)
        total_truncated_tokens = sum(c.get("truncated_token_count", 0) for c in selected_chunks)
        truncated_count = sum(1 for c in selected_chunks if c.get("was_truncated", False))

        logger.info("✅ Token budgeting complete:")
        logger.info(f"   Selected: {len(selected_chunks)}/{len(raw_chunks)} chunks")
        logger.info(f"   Truncated: {truncated_count} chunks")
        logger.info(
            f"   Tokens: {total_truncated_tokens} (saved {total_original_tokens - total_truncated_tokens})"
        )

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
            analysis_dict = await parse_llm_json_response_async(
                llm_response, expected_type="object"
            )
        except Exception as parse_error:
            logger.error(f"❌ Failed to parse JSON response: {parse_error}")
            logger.error(f"   Original response: {llm_response[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {parse_error}") from parse_error

        # Step 4: Create RepoAnalysis object
        repo_analysis: RepoAnalysis = {
            "summary": analysis_dict.get("summary", ""),
            "primary_language": analysis_dict.get("primary_language", ""),
            "frameworks": analysis_dict.get("frameworks", []),
            "architecture_patterns": analysis_dict.get("architecture_patterns", []),
            "difficulty": analysis_dict.get("difficulty", "intermediate"),
        }

        logger.info("✅ Repository analysis complete:")
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
