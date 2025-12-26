from typing import List, Dict
from supabase import Client
from app.core.supabase_client import get_supabase_client


def store_chunks(
    project_id: str,
    chunks: List[Dict]
) -> List[str]:
    """
    Bulk insert chunks into Supabase and return chunk IDs.
    """
    supabase: Client = get_supabase_client()

    rows = []
    for chunk in chunks:
        rows.append({
            "project_id": project_id,
            "file_path": chunk["file_path"],
            "chunk_index": chunk["chunk_index"],
            "language": chunk["language"],
            "content": chunk["content"],
            "token_count": chunk["token_count"],
        })

    response = supabase.table("project_chunks").insert(rows).execute()

    if response.error:
        raise RuntimeError(f"Failed to store chunks: {response.error}")

    return [row["id"] for row in response.data]
