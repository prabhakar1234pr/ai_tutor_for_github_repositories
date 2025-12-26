import logging
import time
from app.services.github_service import fetch_repository_files
from app.utils.text_chunking import chunk_files
from app.services.chunk_storage import store_chunks
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService, COLLECTION_NAME
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


async def run_embedding_pipeline(
    project_id: str,
    github_url: str,
):
    start_time = time.time()
    logger.info(f"🚀 Starting embedding pipeline for project_id={project_id}, github_url={github_url}")
    
    supabase = get_supabase_client()
    embedding_service = EmbeddingService()
    qdrant_service = QdrantService()

    try:
        # Step 1: mark project as processing
        logger.info(f"📝 Step 1/7: Updating project status to 'processing' for project_id={project_id}")
        supabase.table("Projects").update(
            {"status": "processing"}
        ).eq("project_id", project_id).execute()
        logger.info(f"✅ Step 1/7: Project status updated to 'processing'")

        # Step 2: fetch repo files
        logger.info(f"📥 Step 2/7: Fetching repository files from {github_url}")
        fetch_start = time.time()
        files = await fetch_repository_files(github_url)
        fetch_duration = time.time() - fetch_start
        total_size = sum(len(f["content"].encode("utf-8")) for f in files)
        logger.info(f"✅ Step 2/7: Fetched {len(files)} files ({total_size / 1024:.1f} KB) in {fetch_duration:.2f}s")

        # Step 3: chunk files
        logger.info(f"✂️  Step 3/7: Chunking {len(files)} files into text chunks")
        chunk_start = time.time()
        chunks = chunk_files(project_id=project_id, files=files)
        chunk_duration = time.time() - chunk_start
        total_tokens = sum(c["token_count"] for c in chunks)
        logger.info(f"✅ Step 3/7: Created {len(chunks)} chunks ({total_tokens:,} total tokens) in {chunk_duration:.2f}s")
        logger.debug(f"   Average chunk size: {total_tokens // len(chunks) if chunks else 0} tokens")

        # Step 4: store chunks in Supabase
        logger.info(f"💾 Step 4/7: Storing {len(chunks)} chunks in Supabase")
        store_start = time.time()
        chunk_ids = store_chunks(project_id, chunks)
        store_duration = time.time() - store_start
        logger.info(f"✅ Step 4/7: Stored {len(chunk_ids)} chunks in Supabase in {store_duration:.2f}s")
        logger.debug(f"   First chunk_id: {chunk_ids[0] if chunk_ids else 'N/A'}, Last chunk_id: {chunk_ids[-1] if chunk_ids else 'N/A'}")

        # Step 5: generate embeddings
        logger.info(f"🧮 Step 5/7: Generating embeddings for {len(chunks)} chunks")
        embed_start = time.time()
        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_texts(texts)
        embed_duration = time.time() - embed_start
        logger.info(f"✅ Step 5/7: Generated {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0}) in {embed_duration:.2f}s")
        logger.debug(f"   Embedding generation rate: {len(embeddings) / embed_duration:.1f} embeddings/sec")

        # Step 6: upsert into Qdrant
        logger.info(f"🔍 Step 6/7: Upserting {len(embeddings)} embeddings into Qdrant")
        metadatas = [
            {"file_path": c["file_path"], "language": c["language"]}
            for c in chunks
        ]
        qdrant_start = time.time()
        qdrant_service.upsert_embeddings(
            project_id=project_id,
            chunk_ids=chunk_ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        qdrant_duration = time.time() - qdrant_start
        logger.info(f"✅ Step 6/7: Upserted {len(embeddings)} embeddings into Qdrant in {qdrant_duration:.2f}s")

        # Step 7: mark project ready
        logger.info(f"✅ Step 7/7: Updating project status to 'ready' for project_id={project_id}")
        supabase.table("Projects").update(
            {"status": "ready"}
        ).eq("project_id", project_id).execute()
        logger.info(f"✅ Step 7/7: Project status updated to 'ready'")

        total_duration = time.time() - start_time
        logger.info(f"🎉 Embedding pipeline completed successfully for project_id={project_id} in {total_duration:.2f}s")
        logger.info(f"📊 Pipeline Summary:")
        logger.info(f"   • Files processed: {len(files)}")
        logger.info(f"   • Chunks created: {len(chunks)}")
        logger.info(f"   • Chunks stored in Supabase: {len(chunk_ids)}")
        logger.info(f"   • Embeddings generated: {len(embeddings)}")
        logger.info(f"   • Points stored in Qdrant: {len(embeddings)} (collection: {COLLECTION_NAME})")
        logger.info(f"   • Total tokens: {sum(c['token_count'] for c in chunks):,}")
        logger.info(f"   • Total duration: {total_duration:.2f}s")

    except Exception as e:
        error_duration = time.time() - start_time
        logger.error(f"❌ Embedding pipeline failed for project_id={project_id} after {error_duration:.2f}s: {str(e)}", exc_info=True)
        
        # Try to update with error_reason, but if column doesn't exist, just update status
        try:
            logger.info(f"📝 Updating project status to 'failed' with error_reason")
            supabase.table("Projects").update(
                {
                    "status": "failed",
                    "error_reason": str(e),
                }
            ).eq("project_id", project_id).execute()
            logger.info(f"✅ Project status updated to 'failed'")
        except Exception as update_error:
            logger.warning(f"⚠️  Failed to update with error_reason, trying without it: {update_error}")
            # If error_reason column doesn't exist, just update status
            try:
                supabase.table("Projects").update(
                    {"status": "failed"}
                ).eq("project_id", project_id).execute()
                logger.info(f"✅ Project status updated to 'failed' (without error_reason)")
            except Exception as final_error:
                logger.error(f"❌ Failed to update project status: {final_error}")
        raise
