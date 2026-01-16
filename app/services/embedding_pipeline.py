import logging
import time

from app.core.supabase_client import get_supabase_client
from app.services.chunk_storage import store_chunks
from app.services.embedding_service import get_embedding_service
from app.services.github_service import fetch_repository_files
from app.services.qdrant_service import COLLECTION_NAME, get_qdrant_service
from app.utils.text_chunking import chunk_files
from app.utils.time_estimation import log_time_estimate

logger = logging.getLogger(__name__)


async def run_embedding_pipeline(
    project_id: str,
    github_url: str,
    api_start_time: float = None,
):
    """
    Run the complete embedding pipeline for a project.

    Args:
        project_id: UUID of the project
        github_url: GitHub repository URL
        api_start_time: Timestamp when user clicked "Let's start building" (for total timing)
    """
    pipeline_start_time = time.time()

    # If api_start_time is provided, calculate time from API call
    if api_start_time:
        time_from_api = pipeline_start_time - api_start_time
        logger.info(f"⏱️  [TIMING] Pipeline started {time_from_api:.3f}s after API call")

    logger.info(
        f"🚀 Starting embedding pipeline for project_id={project_id}, github_url={github_url}"
    )
    logger.info(f"⏱️  [TIMING] Pipeline start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    supabase = get_supabase_client()
    # Use lazy singletons - models/services loaded only on first use, then reused
    embedding_service = get_embedding_service()
    qdrant_service = get_qdrant_service()

    try:
        # Step 1: mark project as processing
        logger.info(
            f"📝 Step 1/7: Updating project status to 'processing' for project_id={project_id}"
        )
        supabase.table("Projects").update({"status": "processing"}).eq(
            "project_id", project_id
        ).execute()
        logger.info("✅ Step 1/7: Project status updated to 'processing'")

        # Step 2: fetch repo files
        logger.info(f"📥 Step 2/7: Fetching repository files from {github_url}")
        fetch_start = time.time()
        files = await fetch_repository_files(github_url)
        fetch_duration = time.time() - fetch_start

        # Calculate total size in bytes and MB
        total_size_bytes = sum(len(f["content"].encode("utf-8")) for f in files)
        total_size_mb = total_size_bytes / (1024 * 1024)
        total_size_kb = total_size_bytes / 1024

        # Calculate cumulative time from pipeline start
        cumulative_time = time.time() - pipeline_start_time
        if api_start_time:
            total_time_from_api = time.time() - api_start_time
            logger.info(
                f"⏱️  [TIMING] Step 2 completed - Cumulative: {cumulative_time:.3f}s | Total from API: {total_time_from_api:.3f}s"
            )

        logger.info(
            f"✅ Step 2/7: Fetched {len(files)} files ({total_size_kb:.1f} KB / {total_size_mb:.2f} MB) in {fetch_duration:.2f}s"
        )
        if fetch_duration > 0:
            logger.info(
                f"📊 [METRICS] Repository size: {total_size_mb:.2f} MB | Files: {len(files)} | Fetch rate: {total_size_mb / fetch_duration:.2f} MB/s"
            )

        # Log time estimate based on repository size
        log_time_estimate(total_size_mb)

        # Step 3: chunk files
        logger.info(f"✂️  Step 3/7: Chunking {len(files)} files into text chunks")
        chunk_start = time.time()
        chunks = chunk_files(project_id=project_id, files=files)
        chunk_duration = time.time() - chunk_start
        total_tokens = sum(c["token_count"] for c in chunks)

        # Calculate cumulative time
        cumulative_time = time.time() - pipeline_start_time
        if api_start_time:
            total_time_from_api = time.time() - api_start_time
            logger.info(
                f"⏱️  [TIMING] Step 3 completed - Cumulative: {cumulative_time:.3f}s | Total from API: {total_time_from_api:.3f}s"
            )

        logger.info(
            f"✅ Step 3/7: Created {len(chunks)} chunks ({total_tokens:,} total tokens) in {chunk_duration:.2f}s"
        )
        if chunk_duration > 0:
            logger.info(
                f"📊 [METRICS] Chunking rate: {len(chunks) / chunk_duration:.1f} chunks/s | {total_size_mb / chunk_duration:.2f} MB/s"
            )
        logger.debug(
            f"   Average chunk size: {total_tokens // len(chunks) if chunks else 0} tokens"
        )

        # Step 4: store chunks in Supabase
        logger.info(f"💾 Step 4/7: Storing {len(chunks)} chunks in Supabase")
        store_start = time.time()
        chunk_ids = store_chunks(project_id, chunks)
        store_duration = time.time() - store_start

        # Calculate cumulative time
        cumulative_time = time.time() - pipeline_start_time
        if api_start_time:
            total_time_from_api = time.time() - api_start_time
            logger.info(
                f"⏱️  [TIMING] Step 4 completed - Cumulative: {cumulative_time:.3f}s | Total from API: {total_time_from_api:.3f}s"
            )
            logger.info(
                f"⏱️  [TIMING] ✅ CHUNKS STORED IN SUPABASE - Time from 'Let's start building': {total_time_from_api:.3f}s ({total_time_from_api / 60:.2f} minutes)"
            )

        logger.info(
            f"✅ Step 4/7: Stored {len(chunk_ids)} chunks in Supabase in {store_duration:.2f}s"
        )
        logger.info(
            f"📊 [METRICS] Storage rate: {len(chunk_ids) / store_duration:.1f} chunks/s | {total_size_mb / store_duration:.2f} MB/s"
            if store_duration > 0
            else ""
        )
        logger.debug(
            f"   First chunk_id: {chunk_ids[0] if chunk_ids else 'N/A'}, Last chunk_id: {chunk_ids[-1] if chunk_ids else 'N/A'}"
        )

        # Step 5: generate embeddings
        logger.info(f"🧮 Step 5/7: Generating embeddings for {len(chunks)} chunks")
        embed_start = time.time()
        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_texts(texts)
        embed_duration = time.time() - embed_start

        # Calculate cumulative time
        cumulative_time = time.time() - pipeline_start_time
        if api_start_time:
            total_time_from_api = time.time() - api_start_time
            logger.info(
                f"⏱️  [TIMING] Step 5 completed - Cumulative: {cumulative_time:.3f}s | Total from API: {total_time_from_api:.3f}s"
            )

        logger.info(
            f"✅ Step 5/7: Generated {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0}) in {embed_duration:.2f}s"
        )
        if embed_duration > 0:
            logger.info(
                f"📊 [METRICS] Embedding rate: {len(embeddings) / embed_duration:.1f} embeddings/s | {total_tokens / embed_duration:.0f} tokens/s"
            )
            logger.debug(
                f"   Embedding generation rate: {len(embeddings) / embed_duration:.1f} embeddings/sec"
            )

        # Step 6: upsert into Qdrant
        logger.info(f"🔍 Step 6/7: Upserting {len(embeddings)} embeddings into Qdrant")
        metadatas = [{"file_path": c["file_path"], "language": c["language"]} for c in chunks]
        qdrant_start = time.time()
        qdrant_service.upsert_embeddings(
            project_id=project_id,
            chunk_ids=chunk_ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        qdrant_duration = time.time() - qdrant_start

        # Calculate cumulative time
        cumulative_time = time.time() - pipeline_start_time
        if api_start_time:
            total_time_from_api = time.time() - api_start_time
            logger.info(
                f"⏱️  [TIMING] Step 6 completed - Cumulative: {cumulative_time:.3f}s | Total from API: {total_time_from_api:.3f}s"
            )
            logger.info(
                f"⏱️  [TIMING] ✅ EMBEDDINGS STORED IN QDRANT - Time from 'Let's start building': {total_time_from_api:.3f}s ({total_time_from_api / 60:.2f} minutes)"
            )

        logger.info(
            f"✅ Step 6/7: Upserted {len(embeddings)} embeddings into Qdrant in {qdrant_duration:.2f}s"
        )
        logger.info(
            f"📊 [METRICS] Qdrant upsert rate: {len(embeddings) / qdrant_duration:.1f} embeddings/s"
            if qdrant_duration > 0
            else ""
        )

        # Step 7: mark project ready
        logger.info(f"✅ Step 7/7: Updating project status to 'ready' for project_id={project_id}")
        supabase.table("Projects").update({"status": "ready"}).eq(
            "project_id", project_id
        ).execute()
        logger.info("✅ Step 7/7: Project status updated to 'ready'")

        # Step 8: Trigger roadmap generation (background task)
        logger.info(f"📚 Step 8/8: Triggering roadmap generation for project_id={project_id}")
        try:
            from app.services.roadmap_generation import run_roadmap_generation

            # Get project data for roadmap generation
            project_response = (
                supabase.table("Projects")
                .select("github_url, skill_level, target_days")
                .eq("project_id", project_id)
                .execute()
            )

            if project_response.data:
                project_data = project_response.data[0]
                # Schedule roadmap generation as background task (non-blocking)
                import asyncio

                asyncio.create_task(
                    run_roadmap_generation(
                        project_id=str(project_id),
                        github_url=project_data["github_url"],
                        skill_level=project_data["skill_level"],
                        target_days=project_data["target_days"],
                    )
                )
                logger.info("✅ Step 8/8: Roadmap generation scheduled as background task")
            else:
                logger.warning("⚠️  Could not find project data for roadmap generation")
        except Exception as roadmap_error:
            logger.error(f"❌ Failed to trigger roadmap generation: {roadmap_error}", exc_info=True)
            # Don't fail the embedding pipeline if roadmap generation fails

        total_duration = time.time() - pipeline_start_time

        # Calculate total time from API if available
        total_time_from_api = None
        if api_start_time:
            total_time_from_api = time.time() - api_start_time

        logger.info(
            f"🎉 Embedding pipeline completed successfully for project_id={project_id} in {total_duration:.2f}s"
        )

        # Calculate time breakdown
        if api_start_time and total_time_from_api:
            logger.info("")
            logger.info("=" * 80)
            logger.info("⏱️  [TIMING SUMMARY] Total time from 'Let's start building' to completion")
            logger.info("=" * 80)
            logger.info(
                f"   🎯 Total Time: {total_time_from_api:.3f}s ({total_time_from_api / 60:.2f} minutes)"
            )
            logger.info(
                f"   📥 GitHub Fetch: {fetch_duration:.3f}s ({fetch_duration / total_time_from_api * 100:.1f}%)"
            )
            logger.info(
                f"   ✂️  Chunking: {chunk_duration:.3f}s ({chunk_duration / total_time_from_api * 100:.1f}%)"
            )
            logger.info(
                f"   💾 Supabase Storage: {store_duration:.3f}s ({store_duration / total_time_from_api * 100:.1f}%)"
            )
            logger.info(
                f"   🧮 Embedding Generation: {embed_duration:.3f}s ({embed_duration / total_time_from_api * 100:.1f}%)"
            )
            logger.info(
                f"   🔍 Qdrant Storage: {qdrant_duration:.3f}s ({qdrant_duration / total_time_from_api * 100:.1f}%)"
            )
            logger.info(
                f"   ⚙️  Other (status updates, etc.): {total_time_from_api - fetch_duration - chunk_duration - store_duration - embed_duration - qdrant_duration:.3f}s"
            )
            logger.info("=" * 80)

        logger.info("📊 Pipeline Summary:")
        logger.info(f"   • Repository size: {total_size_mb:.2f} MB ({total_size_kb:.1f} KB)")
        logger.info(f"   • Files processed: {len(files)}")
        logger.info(f"   • Chunks created: {len(chunks)}")
        logger.info(f"   • Chunks stored in Supabase: {len(chunk_ids)}")
        logger.info(f"   • Embeddings generated: {len(embeddings)}")
        logger.info(
            f"   • Points stored in Qdrant: {len(embeddings)} (collection: {COLLECTION_NAME})"
        )
        logger.info(f"   • Total tokens: {total_tokens:,}")
        logger.info(f"   • Pipeline duration: {total_duration:.2f}s")

        # Calculate and log performance metrics for estimation formula
        if total_size_mb > 0 and total_time_from_api and total_time_from_api > 0:
            mb_per_second = total_size_mb / total_time_from_api
            logger.info("")
            logger.info("📈 [PERFORMANCE METRICS]")
            logger.info(f"   • Processing speed: {mb_per_second:.2f} MB/s")
            logger.info(f"   • Files per second: {len(files) / total_time_from_api:.1f} files/s")
            logger.info(f"   • Chunks per second: {len(chunks) / total_time_from_api:.1f} chunks/s")
            logger.info(
                f"   • Tokens per second: {total_tokens / total_time_from_api:.0f} tokens/s"
            )

            # Estimation formula
            logger.info("")
            logger.info("🔮 [ESTIMATION FORMULA] Based on current processing speed:")
            logger.info(f"   Estimated time (seconds) = Repository Size (MB) / {mb_per_second:.2f}")
            logger.info(
                f"   Estimated time (minutes) = Repository Size (MB) / {mb_per_second:.2f} / 60"
            )
            logger.info("")
            logger.info("   Examples:")
            logger.info(
                f"   • 200 MB repo: ~{200 / mb_per_second:.1f}s ({200 / mb_per_second / 60:.1f} min)"
            )
            logger.info(
                f"   • 500 MB repo: ~{500 / mb_per_second:.1f}s ({500 / mb_per_second / 60:.1f} min)"
            )
            logger.info(
                f"   • 1 GB repo: ~{1024 / mb_per_second:.1f}s ({1024 / mb_per_second / 60:.1f} min)"
            )

            # Compare actual vs estimated
            from app.utils.time_estimation import estimate_processing_time

            estimated = estimate_processing_time(total_size_mb)
            logger.info("")
            logger.info("📊 [ACTUAL vs ESTIMATED]")
            logger.info(
                f"   Actual time: {total_time_from_api:.1f}s ({total_time_from_api / 60:.1f} min)"
            )
            logger.info(
                f"   Estimated time: {estimated['total_seconds']:.1f}s ({estimated['total_minutes']:.1f} min)"
            )
            accuracy = (
                1 - abs(total_time_from_api - estimated["total_seconds"]) / total_time_from_api
            ) * 100
            logger.info(f"   Estimation accuracy: {accuracy:.1f}%")

    except Exception as e:
        error_duration = time.time() - pipeline_start_time
        if api_start_time:
            total_time_from_api = time.time() - api_start_time
            logger.error(f"❌ Embedding pipeline failed for project_id={project_id}")
            logger.error(
                f"⏱️  [TIMING] Failed after {error_duration:.2f}s (pipeline) / {total_time_from_api:.2f}s (total from API)"
            )
        else:
            logger.error(
                f"❌ Embedding pipeline failed for project_id={project_id} after {error_duration:.2f}s: {str(e)}",
                exc_info=True,
            )

        # Update project status to failed with error message
        try:
            logger.info("📝 Updating project status to 'failed' with error_message")
            supabase.table("Projects").update(
                {
                    "status": "failed",
                    "error_message": str(e)[:500],  # Limit error message length
                }
            ).eq("project_id", project_id).execute()
            logger.info("✅ Project status updated to 'failed'")
        except Exception as update_error:
            logger.error(f"❌ Failed to update project status: {update_error}")
        raise
