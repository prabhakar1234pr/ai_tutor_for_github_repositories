from typing import List, Dict
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue
from app.core.qdrant_client import get_qdrant_client

COLLECTION_NAME = "gitguide_chunks"
VECTOR_SIZE = 384


class QdrantService:
    def __init__(self):
        self.client = get_qdrant_client()
        self._ensure_collection()

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        if COLLECTION_NAME not in [c.name for c in collections]:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "size": VECTOR_SIZE,
                    "distance": "Cosine",
                },
            )

    def upsert_embeddings(
        self,
        project_id: str,
        chunk_ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ):
        points = []

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

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )

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
