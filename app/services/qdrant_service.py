import logging
import time
import uuid
from typing import List, Dict, Union
from qdrant_client.http.models import (
    PointStruct, 
    Filter, 
    FieldCondition, 
    MatchValue, 
    PointsSelector, 
    PointIdsList,
    FilterSelector
)
from app.core.qdrant_client import get_qdrant_client

logger = logging.getLogger(__name__)

COLLECTION_NAME = "gitguide_chunks"
VECTOR_SIZE = 384

# Lazy singleton instance
_qdrant_service_instance = None


def get_qdrant_service() -> 'QdrantService':
    """
    Get or create singleton QdrantService instance (lazy initialization).
    
    The collection check/creation happens only on first use, then reused for all subsequent requests.
    This saves 1-2 seconds per request after the first one.
    
    Returns:
        QdrantService: Singleton instance with initialized collection
    """
    global _qdrant_service_instance
    
    if _qdrant_service_instance is None:
        logger.info(f"🔍 Initializing QdrantService (first use)...")
        _qdrant_service_instance = QdrantService()
        logger.info(f"✅ QdrantService ready (will reuse for future requests)")
    
    return _qdrant_service_instance


class QdrantService:
    def __init__(self, skip_collection_check: bool = False):
        """
        Initialize QdrantService.
        
        Args:
            skip_collection_check: If True, skip collection check (for testing or when called from singleton)
        """
        logger.info(f"🔍 Initializing QdrantService for collection: {COLLECTION_NAME}")
        self.client = get_qdrant_client()
        if not skip_collection_check:
            self._ensure_collection()
        logger.info(f"✅ QdrantService initialized successfully")

    def _ensure_collection(self):
        logger.debug(f"🔍 Checking if collection '{COLLECTION_NAME}' exists")
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        collection_created = False
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
            collection_created = True
        else:
            logger.debug(f"✅ Collection '{COLLECTION_NAME}' already exists")
        
        # Ensure index exists on project_id field for efficient filtering
        # This is critical for filter operations (delete, search)
        try:
            self.client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="project_id",
                field_schema="keyword",  # Use 'keyword' for exact match filtering
            )
            if collection_created:
                logger.info(f"✅ Created index on 'project_id' field")
            else:
                logger.debug(f"✅ Index on 'project_id' verified/created")
        except Exception as e:
            error_msg = str(e).lower()
            # Index might already exist, which is fine
            if "already exists" in error_msg or "duplicate" in error_msg:
                logger.debug(f"   Index on 'project_id' already exists (this is fine)")
            else:
                logger.warning(f"⚠️  Failed to create/verify index on 'project_id': {e}")
                # Continue anyway - the code handles missing index gracefully

    def upsert_embeddings(
        self,
        project_id: str,
        chunk_ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
    ):
        # Issue 4: Handle empty inputs with validation
        if not chunk_ids or not embeddings:
            logger.warning(f"⚠️  No embeddings to upsert (chunk_ids={len(chunk_ids)}, embeddings={len(embeddings)})")
            return
        
        # Validate lengths match
        if len(chunk_ids) != len(embeddings) or len(chunk_ids) != len(metadatas):
            raise ValueError(
                f"Mismatched lengths: chunk_ids={len(chunk_ids)}, "
                f"embeddings={len(embeddings)}, metadatas={len(metadatas)}"
            )
        
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

        # Issue 1: Validate and convert chunk IDs to proper UUID format
        for i in range(len(chunk_ids)):
            chunk_id = chunk_ids[i]
            point_id: Union[str, int]
            
            # Validate and convert to UUID if it's a string
            try:
                if isinstance(chunk_id, str):
                    # Validate UUID format - this will raise ValueError if invalid
                    uuid.UUID(chunk_id)
                    point_id = chunk_id  # Use as string UUID (Qdrant accepts UUID strings)
                elif isinstance(chunk_id, int):
                    point_id = chunk_id  # Use as integer (Qdrant also accepts integers)
                else:
                    # Try to convert to UUID string
                    point_id = str(uuid.UUID(str(chunk_id)))
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Invalid chunk_id format at index {i}: {chunk_id} - {e}")
                raise ValueError(
                    f"chunk_id must be a valid UUID (string) or integer, "
                    f"got: {chunk_id} (type: {type(chunk_id).__name__})"
                )
            
            points.append(
                PointStruct(
                    id=point_id,  # Now guaranteed to be UUID string or integer
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
            if upsert_duration > 0:
                logger.info(f"📊 [METRICS] Qdrant upsert rate: {len(points) / upsert_duration:.1f} points/sec")
                logger.debug(f"   Upsert rate: {len(points) / upsert_duration:.1f} points/sec")
        except Exception as e:
            logger.error(f"❌ Failed to upsert embeddings into Qdrant: {e}", exc_info=True)
            raise

    def delete_points_by_project_id(self, project_id: str) -> int:
        """
        Delete all points from Qdrant collection that belong to a specific project.
        
        Uses filter-based deletion (requires index on project_id, which is created automatically).
        Falls back to scroll + ID-based deletion if filter operations fail.
        
        Returns:
            Number of points deleted
        """
        logger.info(f"🗑️  Deleting points from Qdrant collection '{COLLECTION_NAME}' for project_id={project_id}")
        
        project_filter = Filter(
            must=[
                FieldCondition(
                    key="project_id",
                    match=MatchValue(value=project_id),
                )
            ]
        )
        
        try:
            # Method 1: Try filter-based deletion (fast, requires index - which we create automatically)
            try:
                # Count points first
                test_count = self.client.count(
                    collection_name=COLLECTION_NAME,
                    count_filter=project_filter,
                )
                point_count = test_count.count if hasattr(test_count, 'count') else test_count
                
                if point_count == 0:
                    logger.info(f"✅ No points found for project_id={project_id}")
                    return 0
                
                logger.info(f"   Found {point_count} points to delete")
                logger.debug(f"   Attempting filter-based deletion (requires index)")
                
                delete_start = time.time()
                self.client.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=FilterSelector(filter=project_filter),
                )
                delete_duration = time.time() - delete_start
                
                # Verify deletion
                verify_count = self.client.count(
                    collection_name=COLLECTION_NAME,
                    count_filter=project_filter,
                )
                remaining = verify_count.count if hasattr(verify_count, 'count') else verify_count
                
                if remaining == 0:
                    logger.info(f"✅ Successfully deleted {point_count} points using filter in {delete_duration:.2f}s")
                    return point_count
                else:
                    logger.warning(f"⚠️  Filter deletion incomplete: {remaining} points remain, using fallback method")
                    # Fall through to fallback method
                    
            except Exception as filter_error:
                error_msg = str(filter_error).lower()
                if "index required" in error_msg or "index" in error_msg:
                    logger.warning(f"⚠️  Index not available (unexpected - index should be auto-created), using fallback")
                else:
                    logger.warning(f"⚠️  Filter-based deletion failed: {filter_error}, using fallback")
            
            # Method 2: Fallback - Scroll with filter and delete by IDs (still efficient with index)
            logger.debug(f"   Using fallback: scroll with filter and delete by IDs")
            all_point_ids = []
            scroll_limit = 1000
            offset = None
            
            while True:
                try:
                    scroll_result = self.client.scroll(
                        collection_name=COLLECTION_NAME,
                        limit=scroll_limit,
                        offset=offset,
                        scroll_filter=project_filter,  # Use filter if index exists, otherwise will fail gracefully
                        with_payload=False,  # Don't need payload, just IDs
                        with_vectors=False,
                    )
                    points, next_offset = scroll_result
                    
                    if not points:
                        break
                    
                    batch_ids = [point.id for point in points]
                    all_point_ids.extend(batch_ids)
                    
                    if next_offset is None:
                        break
                    offset = next_offset
                    
                except Exception as scroll_error:
                    # If scroll with filter fails (no index), fall back to scrolling all and filtering in memory
                    error_msg = str(scroll_error).lower()
                    if "index required" in error_msg or "index" in error_msg:
                        logger.debug(f"   Scroll with filter failed (no index), scrolling all points and filtering in memory")
                        offset = None  # Reset offset
                        while True:
                            scroll_result = self.client.scroll(
                                collection_name=COLLECTION_NAME,
                                limit=scroll_limit,
                                offset=offset,
                                with_payload=True,  # Need payload to filter
                                with_vectors=False,
                            )
                            points, next_offset = scroll_result
                            
                            if not points:
                                break
                            
                            # Filter in memory
                            matching_points = [
                                point for point in points
                                if point.payload and point.payload.get("project_id") == project_id
                            ]
                            batch_ids = [point.id for point in matching_points]
                            all_point_ids.extend(batch_ids)
                            
                            if next_offset is None:
                                break
                            offset = next_offset
                    else:
                        logger.error(f"   ❌ Error during scroll: {scroll_error}", exc_info=True)
                    break
            
            if not all_point_ids:
                logger.info(f"✅ No points found for project_id={project_id}")
                return 0
            
            logger.info(f"   Found {len(all_point_ids)} points to delete (fallback method)")
            
            # Delete points in batches
            batch_size = 1000
            delete_start = time.time()
            deleted_count = 0
            
            for i in range(0, len(all_point_ids), batch_size):
                batch = all_point_ids[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(all_point_ids) + batch_size - 1) // batch_size
                
                try:
                    self.client.delete(
                        collection_name=COLLECTION_NAME,
                        points_selector=PointIdsList(points=batch),
                    )
                    deleted_count += len(batch)
                except Exception as batch_error:
                    logger.error(f"   ❌ Failed to delete batch {batch_num}/{total_batches}: {batch_error}", exc_info=True)
                    continue
            
            delete_duration = time.time() - delete_start
            logger.info(f"✅ Successfully deleted {deleted_count} points in {delete_duration:.2f}s (fallback method)")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Failed to delete points from Qdrant: {e}", exc_info=True)
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
