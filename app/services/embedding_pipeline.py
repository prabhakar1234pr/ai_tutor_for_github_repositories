from app.services.github_service import fetch_repository_files
from app.utils.text_chunking import chunk_files
from app.services.chunk_storage import store_chunks
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from app.core.supabase_client import get_supabase_client


async def run_embedding_pipeline(
    project_id: str,
    github_url: str,
):
    supabase = get_supabase_client()
    embedding_service = EmbeddingService()
    qdrant_service = QdrantService()

    try:
        # Step 1: mark project as processing
        supabase.table("Projects").update(
            {"status": "processing"}
        ).eq("project_id", project_id).execute()

        # Step 2: fetch repo files
        files = await fetch_repository_files(github_url)

        # Step 3: chunk files
        chunks = chunk_files(project_id=project_id, files=files)

        # Step 4: store chunks in Supabase
        chunk_ids = store_chunks(project_id, chunks)

        # Step 5: generate embeddings
        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.embed_texts(texts)

        # Step 6: upsert into Qdrant
        metadatas = [
            {"file_path": c["file_path"], "language": c["language"]}
            for c in chunks
        ]

        qdrant_service.upsert_embeddings(
            project_id=project_id,
            chunk_ids=chunk_ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Step 7: mark project ready
        supabase.table("Projects").update(
            {"status": "ready"}
        ).eq("project_id", project_id).execute()

    except Exception as e:
        supabase.table("Projects").update(
            {
                "status": "failed",
                "error_reason": str(e),
            }
        ).eq("project_id", project_id).execute()
        raise
