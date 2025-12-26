from typing import List, Dict
import tiktoken
from app.config import settings

# Initialize tokenizer once
# cl100k_base works well for most modern LLMs
_tokenizer = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return token count for a given text."""
    return len(_tokenizer.encode(text))


def chunk_text(
    *,
    project_id: str,
    file_path: str,
    content: str,
    language: str,
) -> List[Dict]:
    """
    Split a single file into token-based chunks.

    Returns a list of chunks with metadata ready for DB insertion.
    """

    chunk_size = settings.chunk_size          # e.g. 500
    chunk_overlap = settings.chunk_overlap    # e.g. 100

    tokens = _tokenizer.encode(content)
    total_tokens = len(tokens)

    chunks: List[Dict] = []
    start = 0
    chunk_index = 0

    while start < total_tokens:
        end = start + chunk_size
        chunk_tokens = tokens[start:end]

        chunk_text = _tokenizer.decode(chunk_tokens)
        token_count = len(chunk_tokens)

        chunks.append({
            "project_id": project_id,
            "file_path": file_path,
            "chunk_index": chunk_index,
            "language": language,
            "content": chunk_text,
            "token_count": token_count,
        })

        chunk_index += 1
        start += chunk_size - chunk_overlap

        if len(chunks) > settings.max_chunks_per_project:
            raise ValueError("Maximum chunk limit exceeded")

    return chunks


def chunk_files(
    *,
    project_id: str,
    files: List[Dict[str, str]],
) -> List[Dict]:
    """
    Chunk multiple files into a flat list of chunks.

    Input:
        files = [
          {
            "file_path": str,
            "content": str,
            "language": str
          }
        ]
    """

    all_chunks: List[Dict] = []

    for file in files:
        file_chunks = chunk_text(
            project_id=project_id,
            file_path=file["file_path"],
            content=file["content"],
            language=file["language"],
        )

        all_chunks.extend(file_chunks)

        if len(all_chunks) > settings.max_chunks_per_project:
            raise ValueError("Maximum chunk limit exceeded")

    return all_chunks
