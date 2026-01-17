"""
Token budgeting utilities for LangGraph agent.
Handles adaptive token budgeting and chunk truncation for analyze_repo node.
"""

import logging

import tiktoken

from app.utils.text_chunking import count_tokens

logger = logging.getLogger(__name__)

# Constants for token budgeting
ANALYZE_REPO_TOKEN_BUDGET = 6_000  # Total token budget for analyze_repo
MAX_CHUNK_TOKENS = 500  # Maximum tokens per chunk
MIN_CHUNKS = 3  # Minimum chunks needed for meaningful analysis

# Initialize tokenizer once (same encoding as text_chunking.py)
_tokenizer = tiktoken.get_encoding("cl100k_base")
logger.debug("🔤 Initialized tiktoken tokenizer for token_budgeting: cl100k_base")


def truncate_chunk(content: str, max_tokens: int = MAX_CHUNK_TOKENS) -> str:
    """
    Hard truncate chunk content to max_tokens, preserving structure.

    Truncates at reasonable boundaries (sentence/line) when possible.
    Uses tiktoken for accurate token counting.

    Args:
        content: Original chunk content
        max_tokens: Maximum tokens allowed (default: MAX_CHUNK_TOKENS)

    Returns:
        Truncated content string
    """
    if not content:
        return content

    # Count tokens
    tokens_count = count_tokens(content)

    # If within limit, return as-is
    if tokens_count <= max_tokens:
        return content

    # Need to truncate - use tiktoken for accurate token truncation
    # Encode to tokens
    tokens = _tokenizer.encode(content)

    # Truncate to max_tokens
    truncated_tokens = tokens[:max_tokens]

    # Decode back to text
    truncated = _tokenizer.decode(truncated_tokens)

    # Try to end at a reasonable boundary (sentence/line/newline)
    # Don't cut too much - at least 70% of max_tokens
    min_length = int(max_tokens * 0.7)

    # Find last newline
    last_newline = truncated.rfind("\n")
    # Find last period
    last_period = truncated.rfind(".")
    # Find last semicolon (code boundary)
    last_semicolon = truncated.rfind(";")

    # Choose best cutoff point
    cutoff = max(last_newline, last_period, last_semicolon)

    if cutoff > min_length:
        truncated = truncated[: cutoff + 1]
        logger.debug(
            f"   Truncated chunk at boundary (cutoff: {cutoff}, tokens: {count_tokens(truncated)})"
        )
    else:
        # Can't find good boundary, use hard truncation
        logger.debug(
            f"   Hard truncated chunk (no good boundary found, tokens: {count_tokens(truncated)})"
        )

    return truncated


def select_chunks_by_budget(
    chunks: list[dict],
    token_budget: int = ANALYZE_REPO_TOKEN_BUDGET,
    max_chunk_tokens: int = MAX_CHUNK_TOKENS,
    min_chunks: int = MIN_CHUNKS,
) -> list[dict]:
    """
    Select chunks based on adaptive token budget.

    Algorithm:
    1. Iterate through chunks (assumed to be ranked by similarity)
    2. Truncate each chunk to max_chunk_tokens
    3. Add to selection if it fits within budget
    4. Stop when budget is exceeded (unless below min_chunks)

    Args:
        chunks: List of chunk dictionaries with 'content' key
        token_budget: Total token budget (default: ANALYZE_REPO_TOKEN_BUDGET)
        max_chunk_tokens: Max tokens per chunk (default: MAX_CHUNK_TOKENS)
        min_chunks: Minimum chunks to include even if over budget (default: MIN_CHUNKS)

    Returns:
        List of selected chunks with truncated content

    Example:
        chunks = [
            {'content': '...', 'file_path': 'file1.py', ...},
            {'content': '...', 'file_path': 'file2.py', ...},
        ]
        selected = select_chunks_by_budget(chunks)
    """
    selected_chunks = []
    current_tokens = 0

    logger.debug(
        f"   Selecting chunks with budget: {token_budget} tokens, "
        f"max per chunk: {max_chunk_tokens}, min chunks: {min_chunks}"
    )

    for i, chunk in enumerate(chunks):
        # Get original content
        original_content = chunk.get("content", "")
        if not original_content:
            logger.warning(f"   Skipping chunk {i}: empty content")
            continue

        # Truncate chunk
        truncated_content = truncate_chunk(original_content, max_chunk_tokens)
        chunk_tokens = count_tokens(truncated_content)

        # Check if adding this chunk would exceed budget
        if current_tokens + chunk_tokens > token_budget:
            # Check if we have minimum chunks
            if len(selected_chunks) >= min_chunks:
                logger.debug(
                    f"   Budget reached after {len(selected_chunks)} chunks "
                    f"({current_tokens} tokens)"
                )
                break
            else:
                # Below minimum, include anyway
                logger.warning(
                    f"   Budget exceeded but below minimum chunks. "
                    f"Including chunk {i} anyway (total: {current_tokens + chunk_tokens} tokens)"
                )

        # Add to selection
        selected_chunk = chunk.copy()
        selected_chunk["content"] = truncated_content
        selected_chunk["original_token_count"] = count_tokens(original_content)
        selected_chunk["truncated_token_count"] = chunk_tokens
        selected_chunk["was_truncated"] = chunk_tokens < count_tokens(original_content)

        selected_chunks.append(selected_chunk)
        current_tokens += chunk_tokens

        logger.debug(
            f"   Added chunk {i + 1}/{len(chunks)}: {chunk.get('file_path', 'unknown')} "
            f"({chunk_tokens} tokens, total: {current_tokens})"
        )

    logger.info(
        f"✅ Selected {len(selected_chunks)} chunks ({current_tokens}/{token_budget} tokens, "
        f"{current_tokens / token_budget * 100:.1f}% of budget)"
    )

    return selected_chunks


def build_context_from_chunks(chunks: list[dict]) -> str:
    """
    Build context string from selected chunks.

    Formats chunks with file path and chunk index for better context.

    Args:
        chunks: List of chunk dictionaries with 'content', 'file_path', 'chunk_index'

    Returns:
        Formatted context string
    """
    context_parts = []

    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        chunk_index = chunk.get("chunk_index", 0)
        content = chunk.get("content", "")
        language = chunk.get("language", "")

        context_parts.append(
            f"[File: {file_path} | Chunk {chunk_index} | Language: {language}]\n{content}\n"
        )

    context = "\n".join(context_parts)

    logger.debug(f"   Built context string ({len(context)} chars, ~{count_tokens(context)} tokens)")

    return context
