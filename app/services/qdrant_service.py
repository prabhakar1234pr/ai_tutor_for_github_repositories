import logging
import time
from typing import List, Dict
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

    def delete_points_by_project_id(self, project_id: str) -> int:
        """
        Delete all points from Qdrant collection that belong to a specific project.
        
        Since Qdrant requires an index on project_id for filter operations, this method
        scrolls through all points, filters by project_id in memory, then deletes by IDs.
        
        Returns:
            Number of points deleted
        """
        logger.info(f"🗑️  Deleting points from Qdrant collection '{COLLECTION_NAME}' for project_id={project_id}")
        
        try:
            # Try filter-based operations first (requires index on project_id)
            project_filter = Filter(
                must=[
                    FieldCondition(
                        key="project_id",
                        match=MatchValue(value=project_id),
                    )
                ]
            )
            
            use_filter = False
            try:
                # Test if filter operations work (requires index)
                logger.debug(f"   Testing if filter operations are available (requires index on project_id)")
                test_count = self.client.count(
                    collection_name=COLLECTION_NAME,
                    count_filter=project_filter,
                )
                use_filter = True
                point_count = test_count.count if hasattr(test_count, 'count') else test_count
                logger.info(f"   Filter operations available: Found {point_count} points to delete")
            except Exception as filter_error:
                error_msg = str(filter_error)
                if "Index required" in error_msg or "index" in error_msg.lower():
                    logger.warning(f"⚠️  No index on 'project_id' field - filter operations not available")
                    logger.info(f"   Will scroll all points and filter by project_id in memory")
                else:
                    logger.warning(f"⚠️  Filter operation failed: {filter_error}")
                use_filter = False
            
            # Method 1: Try filter-based deletion if index exists
            if use_filter:
                try:
                    logger.debug(f"   Attempting filter-based deletion")
                    delete_start = time.time()
                    self.client.delete(
                        collection_name=COLLECTION_NAME,
                        points_selector=FilterSelector(
                            filter=project_filter
                        ),
                    )
                    delete_duration = time.time() - delete_start
                    logger.info(f"✅ Successfully deleted {point_count} points using filter in {delete_duration:.2f}s")
                    
                    # Verify deletion
                    verify_count = self.client.count(
                        collection_name=COLLECTION_NAME,
                        count_filter=project_filter,
                    )
                    remaining = verify_count.count if hasattr(verify_count, 'count') else verify_count
                    
                    if remaining == 0:
                        logger.info(f"✅ Verification: All points deleted successfully")
                        return point_count
                    else:
                        logger.warning(f"⚠️  Verification: {remaining} points still remain, falling back to ID-based deletion")
                        # Fall through to ID-based deletion
                except Exception as filter_delete_error:
                    logger.warning(f"⚠️  Filter-based deletion failed: {filter_delete_error}, falling back to ID-based deletion")
                    use_filter = False
            
            # Method 2: Scroll all points, filter by project_id in memory, delete by IDs
            logger.debug(f"   Using ID-based deletion: scrolling points and filtering in memory")
            all_point_ids = []
            scroll_limit = 1000
            offset = None
            total_scrolled = 0
            
            while True:
                try:
                    # Scroll with filter if available, otherwise scroll all points
                    scroll_kwargs = {
                        "collection_name": COLLECTION_NAME,
                        "limit": scroll_limit,
                        "offset": offset,
                        "with_payload": True,  # Need payload to filter by project_id
                        "with_vectors": False,
                    }
                    
                    if use_filter:
                        scroll_kwargs["scroll_filter"] = project_filter
                    
                    scroll_result = self.client.scroll(**scroll_kwargs)
                    points, next_offset = scroll_result
                    
                    if not points:
                        break
                    
                    # Filter points by project_id if we're scrolling all points
                    if not use_filter:
                        matching_points = [
                            point for point in points
                            if point.payload and point.payload.get("project_id") == project_id
                        ]
                        batch_ids = [point.id for point in matching_points]
                        if batch_ids:
                            logger.debug(f"   Found {len(batch_ids)} matching points in batch (scrolled {len(points)} total)")
                    else:
                        batch_ids = [point.id for point in points]
                    
                    all_point_ids.extend(batch_ids)
                    total_scrolled += len(points)
                    logger.debug(f"   Scrolled {len(points)} points, found {len(batch_ids)} matching (total matching: {len(all_point_ids)})")
                    
                    if next_offset is None:
                        break
                    
                    offset = next_offset
                except Exception as scroll_error:
                    logger.error(f"   ❌ Error during scroll: {scroll_error}", exc_info=True)
                    break
            
            if not all_point_ids:
                logger.info(f"✅ No points found for project_id={project_id} in Qdrant")
                return 0
            
            logger.info(f"   Found {len(all_point_ids)} points to delete (scrolled {total_scrolled} total points)")
            
            # Delete points in batches
            batch_size = 1000
            delete_start = time.time()
            deleted_count = 0
            
            for i in range(0, len(all_point_ids), batch_size):
                batch = all_point_ids[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(all_point_ids) + batch_size - 1) // batch_size
                
                logger.debug(f"   Deleting batch {batch_num}/{total_batches} ({len(batch)} points)")
                
                try:
                    self.client.delete(
                        collection_name=COLLECTION_NAME,
                        points_selector=PointIdsList(points=batch),
                    )
                    deleted_count += len(batch)
                    logger.debug(f"   ✅ Batch {batch_num} deleted successfully")
                except Exception as batch_error:
                    logger.error(f"   ❌ Failed to delete batch {batch_num}: {batch_error}", exc_info=True)
                    # Continue with other batches even if one fails
                    continue
            
            delete_duration = time.time() - delete_start
            
            if deleted_count == len(all_point_ids):
                logger.info(f"✅ Successfully deleted all {deleted_count} points from Qdrant in {delete_duration:.2f}s")
                logger.debug(f"   Deletion rate: {deleted_count / delete_duration:.1f} points/sec")
            else:
                logger.warning(f"⚠️  Deleted {deleted_count} out of {len(all_point_ids)} points (some batches may have failed)")
            
            # Final verification (only if filter is available)
            if use_filter:
                try:
                    verify_count = self.client.count(
                        collection_name=COLLECTION_NAME,
                        count_filter=project_filter,
                    )
                    remaining = verify_count.count if hasattr(verify_count, 'count') else verify_count
                    
                    if remaining > 0:
                        logger.warning(f"⚠️  Final verification: {remaining} points still exist for project_id={project_id}")
                    else:
                        logger.info(f"✅ Final verification: All points deleted successfully")
                except Exception:
                    pass  # Skip verification if filter operations fail
            
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
