import logging
import uuid

from supabase import Client

from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def store_chunks(project_id: str, chunks: list[dict]) -> list[str]:
    """
    Bulk insert chunks into Supabase and return chunk IDs.
    """
    logger.info(f"💾 Storing {len(chunks)} chunks in Supabase for project_id={project_id}")

    # Handle empty chunks list
    if not chunks:
        logger.info("✅ No chunks to store (empty list)")
        return []

    supabase: Client = get_supabase_client()

    rows = []
    total_content_size = 0
    files_represented = set()
    null_bytes_removed = 0

    for chunk in chunks:
        # Sanitize content: remove null bytes that PostgreSQL cannot store
        content = chunk["content"]
        if "\x00" in content or "\u0000" in content:
            original_length = len(content)
            content = content.replace("\x00", "").replace("\u0000", "")
            null_bytes_removed += original_length - len(content)
            logger.debug(
                f"   Removed null bytes from chunk {chunk['chunk_index']} in {chunk['file_path']}"
            )

        content_size = len(content.encode("utf-8"))
        total_content_size += content_size
        files_represented.add(chunk["file_path"])

        rows.append(
            {
                "project_id": project_id,
                "file_path": chunk["file_path"],
                "chunk_index": chunk["chunk_index"],
                "language": chunk["language"],
                "content": content,  # Use sanitized content
                "token_count": chunk["token_count"],
            }
        )

    if null_bytes_removed > 0:
        logger.warning(f"⚠️  Removed {null_bytes_removed} null bytes from chunks before storage")

    logger.debug(f"   Preparing {len(rows)} rows for insertion")
    logger.debug(
        f"   Total content size: {total_content_size / 1024:.1f} KB ({total_content_size / 1024 / 1024:.2f} MB)"
    )
    logger.debug(f"   Files represented: {len(files_represented)} unique files")
    logger.debug(f"   Average chunk size: {total_content_size // len(rows) if rows else 0} bytes")

    try:
        response = supabase.table("project_chunks").insert(rows).execute()

        if not response.data:
            logger.error("❌ Failed to store chunks: No data returned from Supabase")
            raise RuntimeError("Failed to store chunks: No data returned from Supabase")

        # Issue 3: Validate chunk IDs are valid UUIDs
        chunk_ids = []
        for row in response.data:
            chunk_id = row["id"]
            # Validate it's a UUID
            try:
                uuid.UUID(str(chunk_id))  # Validate UUID format
                chunk_ids.append(str(chunk_id))  # Ensure it's a string UUID
            except (ValueError, TypeError) as e:
                logger.error(
                    f"❌ Invalid UUID returned from Supabase: {chunk_id} (type: {type(chunk_id).__name__})"
                )
                raise ValueError(
                    f"Invalid UUID format for chunk_id returned from Supabase: {chunk_id} - {e}"
                ) from e

        logger.info(f"✅ Successfully stored {len(chunk_ids)} chunks in Supabase")
        logger.debug(f"   First chunk_id: {chunk_ids[0] if chunk_ids else 'N/A'}")
        logger.debug(f"   Last chunk_id: {chunk_ids[-1] if chunk_ids else 'N/A'}")

        return chunk_ids

    except Exception as e:
        logger.error(f"❌ Error storing chunks in Supabase: {e}", exc_info=True)
        raise
