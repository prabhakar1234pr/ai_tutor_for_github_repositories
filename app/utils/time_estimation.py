"""
Utility functions for estimating processing time based on repository size.
"""
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


def estimate_processing_time(
    repository_size_mb: float,
    historical_data: Dict[str, float] = None
) -> Dict[str, float]:
    """
    Estimate processing time for a repository based on its size.
    
    Args:
        repository_size_mb: Size of repository in MB
        historical_data: Optional dict with historical performance metrics:
            - 'mb_per_second': Average MB processed per second
            - 'base_time_seconds': Base overhead time in seconds
    
    Returns:
        Dict with estimated times:
            - 'total_seconds': Total estimated time in seconds
            - 'total_minutes': Total estimated time in minutes
            - 'fetch_seconds': Estimated GitHub fetch time
            - 'chunk_seconds': Estimated chunking time
            - 'storage_seconds': Estimated Supabase storage time
            - 'embedding_seconds': Estimated embedding generation time
            - 'qdrant_seconds': Estimated Qdrant storage time
    
    Formula:
        Based on typical performance metrics:
        - GitHub fetch: ~2-5 MB/s (depends on network and GitHub API rate limits)
        - Chunking: ~10-20 MB/s (CPU-bound, fast)
        - Supabase storage: ~1-3 MB/s (network + database write)
        - Embedding: ~0.5-1 MB/s (GPU/CPU intensive, slowest step)
        - Qdrant storage: ~2-5 MB/s (network + vector DB write)
        
        Base overhead: ~5-10 seconds (API call, status updates, etc.)
    """
    
    # Default performance metrics (can be updated based on historical data)
    if historical_data:
        mb_per_second = historical_data.get('mb_per_second', 1.0)
        base_time = historical_data.get('base_time_seconds', 5.0)
    else:
        # Conservative estimates based on typical performance
        mb_per_second = 1.0  # Overall average processing speed
        base_time = 5.0  # Base overhead time
    
    # Step-specific performance rates (MB/s)
    fetch_rate = 3.0      # GitHub API fetch
    chunk_rate = 15.0     # Text chunking (CPU-bound, fast)
    storage_rate = 2.0    # Supabase storage (network + DB)
    embedding_rate = 0.8  # Embedding generation (ML model, slowest)
    qdrant_rate = 3.0     # Qdrant storage (vector DB)
    
    # Calculate time for each step
    fetch_time = repository_size_mb / fetch_rate if fetch_rate > 0 else 0
    chunk_time = repository_size_mb / chunk_rate if chunk_rate > 0 else 0
    storage_time = repository_size_mb / storage_rate if storage_rate > 0 else 0
    embedding_time = repository_size_mb / embedding_rate if embedding_rate > 0 else 0
    qdrant_time = repository_size_mb / qdrant_rate if qdrant_rate > 0 else 0
    
    # Total time = sum of all steps + base overhead
    total_time = fetch_time + chunk_time + storage_time + embedding_time + qdrant_time + base_time
    
    return {
        'total_seconds': total_time,
        'total_minutes': total_time / 60,
        'fetch_seconds': fetch_time,
        'chunk_seconds': chunk_time,
        'storage_seconds': storage_time,
        'embedding_seconds': embedding_time,
        'qdrant_seconds': qdrant_time,
        'base_overhead_seconds': base_time,
        'estimated_mb_per_second': repository_size_mb / total_time if total_time > 0 else 0
    }


def format_time_estimate(estimate: Dict[str, float]) -> str:
    """
    Format time estimate as a human-readable string.
    """
    total_sec = estimate['total_seconds']
    total_min = estimate['total_minutes']
    
    if total_min < 1:
        return f"~{total_sec:.1f} seconds"
    elif total_min < 60:
        return f"~{total_min:.1f} minutes ({total_sec:.0f} seconds)"
    else:
        hours = total_min / 60
        return f"~{hours:.1f} hours ({total_min:.0f} minutes)"


def log_time_estimate(repository_size_mb: float, historical_data: Dict[str, float] = None):
    """
    Log time estimate for a repository.
    """
    estimate = estimate_processing_time(repository_size_mb, historical_data)
    
    logger.info(f"")
    logger.info(f"🔮 [TIME ESTIMATION] For repository size: {repository_size_mb:.2f} MB")
    logger.info(f"   📥 GitHub Fetch: ~{estimate['fetch_seconds']:.1f}s")
    logger.info(f"   ✂️  Chunking: ~{estimate['chunk_seconds']:.1f}s")
    logger.info(f"   💾 Supabase Storage: ~{estimate['storage_seconds']:.1f}s")
    logger.info(f"   🧮 Embedding Generation: ~{estimate['embedding_seconds']:.1f}s")
    logger.info(f"   🔍 Qdrant Storage: ~{estimate['qdrant_seconds']:.1f}s")
    logger.info(f"   ⚙️  Base Overhead: ~{estimate['base_overhead_seconds']:.1f}s")
    logger.info(f"   ⏱️  TOTAL ESTIMATED TIME: {format_time_estimate(estimate)}")
    logger.info(f"   📊 Estimated processing speed: {estimate['estimated_mb_per_second']:.2f} MB/s")
    logger.info(f"")

