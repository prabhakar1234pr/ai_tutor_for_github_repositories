import logging
from typing import List, Dict
from supabase import Client
from app.core.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def store_chunks(
    project_id: str,
    chunks: List[Dict]
) -> List[str]:
    """
    Bulk insert chunks into Supabase and return chunk IDs.
    """
    logger.info(f"💾 Storing {len(chunks)} chunks in Supabase for project_id={project_id}")
    
    supabase: Client = get_supabase_client()

    rows = []
    total_content_size = 0
    files_represented = set()
    
    for chunk in chunks:
        content_size = len(chunk["content"].encode("utf-8"))
        total_content_size += content_size
        files_represented.add(chunk["file_path"])
        
        rows.append({
            "project_id": project_id,
            "file_path": chunk["file_path"],
            "chunk_index": chunk["chunk_index"],
            "language": chunk["language"],
            "content": chunk["content"],
            "token_count": chunk["token_count"],
        })

    logger.debug(f"   Preparing {len(rows)} rows for insertion")
    logger.debug(f"   Total content size: {total_content_size / 1024:.1f} KB ({total_content_size / 1024 / 1024:.2f} MB)")
    logger.debug(f"   Files represented: {len(files_represented)} unique files")
    logger.debug(f"   Average chunk size: {total_content_size // len(rows) if rows else 0} bytes")

    try:
        response = supabase.table("project_chunks").insert(rows).execute()
        
        if not response.data:
            logger.error(f"❌ Failed to store chunks: No data returned from Supabase")
            raise RuntimeError("Failed to store chunks: No data returned from Supabase")

        chunk_ids = [row["id"] for row in response.data]
        logger.info(f"✅ Successfully stored {len(chunk_ids)} chunks in Supabase")
        logger.debug(f"   First chunk_id: {chunk_ids[0] if chunk_ids else 'N/A'}")
        logger.debug(f"   Last chunk_id: {chunk_ids[-1] if chunk_ids else 'N/A'}")
        
        return chunk_ids
        
    except Exception as e:
        logger.error(f"❌ Error storing chunks in Supabase: {e}", exc_info=True)
        raise
