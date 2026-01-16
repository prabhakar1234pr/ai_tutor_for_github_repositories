import logging
import time

from supabase import Client

from app.core.supabase_client import get_supabase_client
from app.services.embedding_service import get_embedding_service
from app.services.groq_service import get_groq_service
from app.services.qdrant_service import get_qdrant_service

logger = logging.getLogger(__name__)


async def generate_rag_response(
    project_id: str,
    query: str,
    conversation_history: list[dict] | None = None,
    top_k: int = 5,
) -> dict:
    """
    Generate a RAG (Retrieval-Augmented Generation) response for a user query.

    Flow:
    1. Generate embedding for user query
    2. Search Qdrant for top-k similar chunks (filtered by project_id)
    3. Retrieve chunk content from Supabase using chunk IDs
    4. Build context string from retrieved chunks
    5. Generate response using Groq API with context

    Args:
        project_id: UUID string of the project
        query: User's question
        conversation_history: List of previous messages [{"role": "user|assistant", "content": "..."}]
        top_k: Number of top chunks to retrieve (default: 5)

    Returns:
        Dict with keys:
            - response: AI-generated response string
            - chunks_used: List of chunks used as context with metadata

    Raises:
        ValueError: If no chunks found for the project
    """
    start_time = time.time()
    logger.info(f"🔍 Starting RAG pipeline for project_id={project_id}")
    logger.debug(f"   Query: {query[:100]}...")
    logger.debug(f"   Top-k: {top_k}")

    if conversation_history is None:
        conversation_history = []

    # Step 1: Generate embedding for user query
    logger.info("📝 Step 1/5: Generating embedding for query")
    embed_start = time.time()
    embedding_service = get_embedding_service()
    query_embeddings = embedding_service.embed_texts([query])

    if not query_embeddings or len(query_embeddings) == 0:
        raise ValueError("Failed to generate embedding for query")

    query_embedding = query_embeddings[0]
    embed_duration = time.time() - embed_start
    logger.info(
        f"✅ Generated query embedding (dim={len(query_embedding)}) in {embed_duration:.3f}s"
    )

    # Step 2: Search Qdrant for similar chunks
    logger.info("🔍 Step 2/5: Searching Qdrant for similar chunks")
    qdrant_start = time.time()
    qdrant_service = get_qdrant_service()
    search_results = qdrant_service.search(
        project_id=project_id,
        query_embedding=query_embedding,
        limit=top_k,
    )
    qdrant_duration = time.time() - qdrant_start

    if not search_results:
        raise ValueError(
            f"No chunks found for project {project_id}. "
            f"Please ensure the embedding pipeline has completed successfully."
        )

    logger.info(f"✅ Found {len(search_results)} similar chunks in {qdrant_duration:.3f}s")

    # Extract chunk IDs and scores from Qdrant results
    chunk_ids = []
    chunk_scores = {}
    chunk_metadata = {}

    for result in search_results:
        chunk_id = str(result.id)
        chunk_ids.append(chunk_id)
        chunk_scores[chunk_id] = result.score
        chunk_metadata[chunk_id] = {
            "file_path": result.payload.get("file_path", "unknown"),
            "language": result.payload.get("language", "unknown"),
            "score": result.score,
        }

    logger.debug(
        f"   Chunk IDs: {chunk_ids[:3]}..." if len(chunk_ids) > 3 else f"   Chunk IDs: {chunk_ids}"
    )

    # Step 3: Retrieve chunk content from Supabase
    logger.info("💾 Step 3/5: Retrieving chunk content from Supabase")
    supabase_start = time.time()
    supabase: Client = get_supabase_client()

    # Query Supabase for chunks by IDs
    chunks_response = (
        supabase.table("project_chunks")
        .select("id, file_path, chunk_index, language, content, token_count")
        .in_("id", chunk_ids)
        .execute()
    )

    if not chunks_response.data:
        raise ValueError(
            f"Chunks not found in Supabase for project {project_id}. "
            f"This may indicate a data inconsistency between Qdrant and Supabase."
        )

    # Create a mapping of chunk_id to chunk data
    chunks_by_id = {str(chunk["id"]): chunk for chunk in chunks_response.data}

    # Ensure we have all chunks (handle case where some chunks might be missing)
    retrieved_chunks = []
    for chunk_id in chunk_ids:
        if chunk_id in chunks_by_id:
            chunk_data = chunks_by_id[chunk_id]
            retrieved_chunks.append(
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
        else:
            logger.warning(f"⚠️  Chunk {chunk_id} found in Qdrant but not in Supabase")

    if not retrieved_chunks:
        raise ValueError("No valid chunks retrieved from Supabase")

    supabase_duration = time.time() - supabase_start
    logger.info(
        f"✅ Retrieved {len(retrieved_chunks)} chunks from Supabase in {supabase_duration:.3f}s"
    )

    # Step 4: Build context string
    logger.info("📚 Step 4/5: Building context from retrieved chunks")
    context_parts = []
    chunks_used = []

    for chunk in retrieved_chunks:
        file_path = chunk["file_path"]
        content = chunk["content"]
        chunk_index = chunk["chunk_index"]
        language = chunk["language"]

        context_parts.append(
            f"[File: {file_path} | Chunk {chunk_index} | Language: {language}]\n{content}\n"
        )

        chunks_used.append(
            {
                "chunk_id": chunk["id"],
                "file_path": file_path,
                "chunk_index": chunk_index,
                "language": language,
                "score": chunk["score"],
            }
        )

    context = "\n".join(context_parts)
    total_context_tokens = sum(chunk["token_count"] for chunk in retrieved_chunks)

    logger.info(f"✅ Built context ({len(context)} chars, ~{total_context_tokens} tokens)")
    logger.debug(f"   Files referenced: {len({c['file_path'] for c in retrieved_chunks})}")

    # Step 5: Generate response using Groq API
    logger.info("🤖 Step 5/5: Generating response with Groq API")
    groq_start = time.time()
    groq_service = get_groq_service()

    # Build system prompt
    system_prompt = (
        "You are an AI tutor helping users understand a codebase. "
        "Answer questions based ONLY on the provided context from the codebase. "
        "If the answer cannot be found in the context, politely say so and don't make up information. "
        "When referencing code, mention the file path. "
        "Be concise but thorough in your explanations."
    )

    # Generate response (use async version)
    response = await groq_service.generate_response_async(
        user_query=query,
        system_prompt=system_prompt,
        context=context,
        conversation_history=conversation_history,
    )

    groq_duration = time.time() - groq_start
    total_duration = time.time() - start_time

    logger.info(f"✅ Generated response in {groq_duration:.3f}s")
    logger.info(f"⏱️  Total RAG pipeline time: {total_duration:.3f}s")
    logger.debug(f"   Response length: {len(response)} chars")

    return {
        "response": response,
        "chunks_used": chunks_used,
    }
