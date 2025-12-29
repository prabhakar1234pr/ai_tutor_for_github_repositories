from unittest.mock import Mock

import pytest


@pytest.mark.asyncio
async def test_generate_rag_response_happy_path(monkeypatch):
    from app.services import rag_pipeline

    # Mock embedding service
    embedding_service = Mock()
    embedding_service.embed_texts.return_value = [[0.1] * 384]
    monkeypatch.setattr(rag_pipeline, "get_embedding_service", lambda: embedding_service)

    # Mock qdrant search results
    p1 = Mock()
    p1.id = "chunk_1"
    p1.score = 0.9
    p1.payload = {"file_path": "a.py", "language": "python"}
    qdrant_service = Mock()
    qdrant_service.search.return_value = [p1]
    monkeypatch.setattr(rag_pipeline, "get_qdrant_service", lambda: qdrant_service)

    # Mock supabase chunk fetch
    supabase = Mock()
    chain = Mock()
    chain.select.return_value = chain
    chain.in_.return_value = chain
    chain.execute.return_value = Mock(
        data=[
            {
                "id": "chunk_1",
                "file_path": "a.py",
                "chunk_index": 0,
                "language": "python",
                "content": "print('hi')",
                "token_count": 3,
            }
        ]
    )
    supabase.table.return_value = chain
    monkeypatch.setattr(rag_pipeline, "get_supabase_client", lambda: supabase)

    # Mock groq response
    groq_service = Mock()
    groq_service.generate_response.return_value = "final answer"
    monkeypatch.setattr(rag_pipeline, "get_groq_service", lambda: groq_service)

    result = await rag_pipeline.generate_rag_response(
        project_id="proj_1",
        query="hi",
        conversation_history=[],
        top_k=1,
    )

    assert result["response"] == "final answer"
    assert len(result["chunks_used"]) == 1
    assert result["chunks_used"][0]["file_path"] == "a.py"
    qdrant_service.search.assert_called_once()
    groq_service.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_generate_rag_response_raises_when_qdrant_empty(monkeypatch):
    from app.services import rag_pipeline

    embedding_service = Mock()
    embedding_service.embed_texts.return_value = [[0.1] * 384]
    monkeypatch.setattr(rag_pipeline, "get_embedding_service", lambda: embedding_service)

    qdrant_service = Mock()
    qdrant_service.search.return_value = []
    monkeypatch.setattr(rag_pipeline, "get_qdrant_service", lambda: qdrant_service)

    with pytest.raises(ValueError):
        await rag_pipeline.generate_rag_response(
            project_id="proj_1",
            query="hi",
            conversation_history=[],
            top_k=1,
        )


