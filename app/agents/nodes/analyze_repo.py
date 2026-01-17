"""
Analyze repository using RAG to understand its structure and technologies.
This node uses Qdrant embeddings to retrieve relevant code context.

Uses two-stage analysis to handle large codebases and avoid payload size limits:
- Stage 1: High-level analysis with top 6 chunks (smaller payload)
- Stage 2: Detailed analysis with preliminary summary + remaining chunks

Optimized with adaptive token budgeting to prevent token limit errors:
- Retrieves more chunks initially (top_k=15)
- Truncates each chunk to MAX_CHUNK_TOKENS (500)
- Selects chunks within ANALYZE_REPO_TOKEN_BUDGET (6000)
- Splits into two batches for two-stage LLM calls
"""

import logging

from app.agents.prompts import REPO_ANALYSIS_STAGE1_PROMPT, REPO_ANALYSIS_STAGE2_PROMPT
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

        # Step 1f: Split chunks into two batches for two-stage analysis
        # First batch: Top 5-7 chunks for high-level analysis
        # Second batch: Remaining chunks for detailed analysis
        FIRST_STAGE_CHUNKS = 6  # Top 6 chunks for first stage

        if len(selected_chunks) <= FIRST_STAGE_CHUNKS:
            # If we have 6 or fewer chunks, use all for Stage 1, none for Stage 2
            first_stage_chunks = selected_chunks
            second_stage_chunks = []
            logger.info(
                f"📊 Two-stage analysis: Stage 1 ({len(first_stage_chunks)} chunks), Stage 2 (0 chunks - all used in Stage 1)"
            )
        else:
            first_stage_chunks = selected_chunks[:FIRST_STAGE_CHUNKS]
            second_stage_chunks = selected_chunks[FIRST_STAGE_CHUNKS:]
            logger.info(
                f"📊 Two-stage analysis: Stage 1 ({len(first_stage_chunks)} chunks), Stage 2 ({len(second_stage_chunks)} chunks)"
            )

    except Exception as e:
        logger.warning(f"⚠️  RAG retrieval failed: {e}. Using empty context.")
        first_stage_chunks = []
        second_stage_chunks = []

    # Step 2: Two-stage LLM analysis
    logger.info("🤖 Starting two-stage repository analysis with LLM...")

    groq_service = get_groq_service()
    system_prompt = (
        "You are an expert software engineer analyzing codebases. "
        "CRITICAL: Return ONLY valid JSON. Do NOT use markdown code blocks. "
        "Do NOT add any text before or after the JSON. Start with { and end with }."
    )

    try:
        # ===== STAGE 1: High-level analysis with first batch =====
        logger.info("📊 Stage 1: High-level analysis with top chunks...")

        if first_stage_chunks:
            stage1_context = build_context_from_chunks(first_stage_chunks)
        else:
            stage1_context = "No code context available."

        stage1_prompt = REPO_ANALYSIS_STAGE1_PROMPT.format(
            github_url=github_url,
            skill_level=skill_level,
            target_days=target_days,
            code_context=stage1_context,
        )

        stage1_response = await groq_service.generate_response_async(
            user_query=stage1_prompt,
            system_prompt=system_prompt,
            context="",
        )

        logger.debug(f"   Stage 1 response length: {len(stage1_response)} chars")

        # Parse Stage 1 response
        try:
            preliminary_analysis = await parse_llm_json_response_async(
                stage1_response, expected_type="object"
            )
            logger.info("✅ Stage 1 complete: High-level analysis obtained")
        except Exception as parse_error:
            logger.error(f"❌ Failed to parse Stage 1 JSON: {parse_error}")
            raise ValueError(f"Invalid JSON in Stage 1: {parse_error}") from parse_error

        # ===== STAGE 2: Detailed analysis with summary + remaining chunks =====
        logger.info("📊 Stage 2: Detailed analysis with preliminary summary + remaining chunks...")

        if second_stage_chunks:
            stage2_context = build_context_from_chunks(second_stage_chunks)
            # Format preliminary analysis as readable text
            preliminary_text = (
                f"Summary: {preliminary_analysis.get('summary', '')}\n"
                f"Primary Language: {preliminary_analysis.get('primary_language', '')}\n"
                f"Frameworks: {', '.join(preliminary_analysis.get('frameworks', []))}\n"
                f"Architecture Patterns: {', '.join(preliminary_analysis.get('architecture_patterns', []))}\n"
                f"Difficulty: {preliminary_analysis.get('difficulty', 'intermediate')}"
            )
        else:
            # No second stage chunks, use preliminary as final
            logger.info("   No additional chunks for Stage 2, using Stage 1 results as final")
            stage2_context = ""
            preliminary_text = (
                f"Summary: {preliminary_analysis.get('summary', '')}\n"
                f"Primary Language: {preliminary_analysis.get('primary_language', '')}\n"
                f"Frameworks: {', '.join(preliminary_analysis.get('frameworks', []))}\n"
                f"Architecture Patterns: {', '.join(preliminary_analysis.get('architecture_patterns', []))}\n"
                f"Difficulty: {preliminary_analysis.get('difficulty', 'intermediate')}"
            )

        stage2_prompt = REPO_ANALYSIS_STAGE2_PROMPT.format(
            github_url=github_url,
            skill_level=skill_level,
            target_days=target_days,
            preliminary_analysis=preliminary_text,
            code_context=stage2_context,
        )

        # Only run Stage 2 if we have additional chunks
        if second_stage_chunks:
            stage2_response = await groq_service.generate_response_async(
                user_query=stage2_prompt,
                system_prompt=system_prompt,
                context="",
            )

            logger.debug(f"   Stage 2 response length: {len(stage2_response)} chars")

            # Parse Stage 2 response
            try:
                final_analysis = await parse_llm_json_response_async(
                    stage2_response, expected_type="object"
                )
                logger.info("✅ Stage 2 complete: Detailed analysis obtained")
            except Exception as parse_error:
                logger.warning(
                    f"⚠️  Failed to parse Stage 2 JSON, using Stage 1 results: {parse_error}"
                )
                # Fallback to Stage 1 results
                final_analysis = preliminary_analysis
        else:
            # No Stage 2, use Stage 1 results
            final_analysis = preliminary_analysis

        # Step 3: Create final RepoAnalysis object
        repo_analysis: RepoAnalysis = {
            "summary": final_analysis.get("summary", ""),
            "primary_language": final_analysis.get("primary_language", ""),
            "frameworks": final_analysis.get("frameworks", []),
            "architecture_patterns": final_analysis.get("architecture_patterns", []),
            "difficulty": final_analysis.get("difficulty", "intermediate"),
        }

        logger.info("✅ Repository analysis complete (two-stage):")
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
