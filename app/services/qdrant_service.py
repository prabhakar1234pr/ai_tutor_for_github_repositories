import logging
import time
from typing import List, Dict
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue
from app.core.qdrant_client import get_qdrant_client

logger = logging.getLogger(__name__)

COLLECTION_NAME = "gitguide_chunks"
VECTOR_SIZE = 384


class QdrantService:
    def __init__(self):
        logger.info(f"🔍 Initializing QdrantService for collection: {COLLECTION_NAME}")
        self.client = get_qdrant_client()
        self._ensure_collection()
        logger.info(f"✅ QdrantService initialized successfully")

    def _ensure_collection(self):
        logger.debug(f"🔍 Checking if collection '{COLLECTION_NAME}' exists")
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if COLLECTION_NAME not in collection_names:
            logger.info(f"📦 Creating new Qdrant collection: {COLLECTION_NAME}")
            logger.debug(f"   Vector size: {VECTOR_SIZE}")
            logger.debug(f"   Distance metric: Cosine")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "size": VECTOR_SIZE,
                    "distance": "Cosine",
                },
            )
            logger.info(f"✅ Collection '{COLLECTION_NAME}' created successfully")
        else:
            logger.debug(f"✅ Collection '{COLLECTION_NAME}' already exists")

    def upsert_embeddings(
        self,
        project_id: str,
        chunk_ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ):
        if not chunk_ids or not embeddings:
            logger.warning(f"⚠️  No embeddings to upsert (chunk_ids={len(chunk_ids)}, embeddings={len(embeddings)})")
            return
        
        logger.info(f"🔍 Upserting {len(embeddings)} embeddings into Qdrant collection '{COLLECTION_NAME}'")
        logger.debug(f"   Project ID: {project_id}")
        logger.debug(f"   Vector dimension: {len(embeddings[0]) if embeddings else 0}")
        
        # Count unique files and languages
        unique_files = set(m["file_path"] for m in metadatas)
        languages = {}
        for m in metadatas:
            lang = m["language"]
            languages[lang] = languages.get(lang, 0) + 1
        
        logger.debug(f"   Unique files: {len(unique_files)}")
        logger.debug(f"   Languages: {dict(languages)}")
        
        points = []
        start_time = time.time()

        for i in range(len(chunk_ids)):
            points.append(
                PointStruct(
                    id=chunk_ids[i],
                    vector=embeddings[i],
                    payload={
                        "project_id": project_id,
                        "file_path": metadatas[i]["file_path"],
                        "language": metadatas[i]["language"],
                    },
                )
            )

        build_duration = time.time() - start_time
        logger.debug(f"   Built {len(points)} PointStruct objects in {build_duration:.3f}s")

        upsert_start = time.time()
        try:
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
            )
            upsert_duration = time.time() - upsert_start
            logger.info(f"✅ Successfully upserted {len(points)} embeddings into Qdrant in {upsert_duration:.2f}s")
            logger.debug(f"   Upsert rate: {len(points) / upsert_duration:.1f} points/sec")
        except Exception as e:
            logger.error(f"❌ Failed to upsert embeddings into Qdrant: {e}", exc_info=True)
            raise

    def search(
        self,
        project_id: str,
        query_embedding: List[float],
        limit: int = 5,
    ):
        return self.client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_embedding,
            limit=limit,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="project_id",
                        match=MatchValue(value=project_id),
                    )
                ]
            ),
        )
