import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chatbot import router as chatbot_router
from app.core.supabase_client import get_supabase_client
from app.utils.clerk_auth import verify_clerk_token


def _make_supabase_mock(*, user_id: str, project_id: str, project_status: str = "ready"):
    """
    Create a Supabase mock that supports the query chains used by the chatbot endpoint.
    """
    supabase = Mock()

    def make_chain(data):
        chain = Mock()
        chain.select = Mock(return_value=chain)
        chain.eq = Mock(return_value=chain)
        chain.execute = Mock(return_value=Mock(data=data))
        return chain

    user_table = Mock()
    user_table.select = Mock(return_value=make_chain([{"id": user_id}]))

    projects_table = Mock()
    projects_table.select = Mock(
        return_value=make_chain(
            [
                {
                    "project_id": project_id,
                    "project_name": "Test Project",
                    "status": project_status,
                    "user_id": user_id,
                }
            ]
        )
    )

    def table(name: str):
        if name == "User":
            return user_table
        if name == "projects":
            return projects_table
        raise AssertionError(f"Unexpected table requested: {name}")

    supabase.table = Mock(side_effect=table)
    return supabase


@pytest.fixture
def chatbot_client(monkeypatch):
    app = FastAPI()
    app.include_router(chatbot_router, prefix="/api/chatbot")

    async def _fake_verify_clerk_token():
        return {"clerk_user_id": "user_123"}

    # We’ll set get_supabase_client per-test via dependency overrides
    app.dependency_overrides[verify_clerk_token] = _fake_verify_clerk_token
    return TestClient(app)


def test_chatbot_success(chatbot_client, monkeypatch):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    supabase = _make_supabase_mock(user_id=user_id, project_id=project_id, project_status="ready")

    # Supabase dependency is synchronous in endpoint signature; return object directly
    chatbot_client.app.dependency_overrides[get_supabase_client] = lambda: supabase

    # Patch RAG pipeline call
    mock_generate = AsyncMock(
        return_value={"response": "hello", "chunks_used": [{"chunk_id": "c1"}]}
    )
    monkeypatch.setattr("app.api.chatbot.generate_rag_response", mock_generate)

    resp = chatbot_client.post(
        f"/api/chatbot/{project_id}/chat",
        json={"message": "hi", "conversation_history": []},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["response"] == "hello"
    assert isinstance(data["chunks_used"], list)
    mock_generate.assert_awaited_once()


def test_chatbot_project_not_ready(chatbot_client, monkeypatch):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    supabase = _make_supabase_mock(
        user_id=user_id, project_id=project_id, project_status="processing"
    )
    chatbot_client.app.dependency_overrides[get_supabase_client] = lambda: supabase

    resp = chatbot_client.post(
        f"/api/chatbot/{project_id}/chat",
        json={"message": "hi", "conversation_history": []},
    )
    assert resp.status_code == 400, resp.text
    assert "not ready" in resp.json()["detail"].lower()


def test_chatbot_rag_value_error_maps_to_404(chatbot_client, monkeypatch):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    supabase = _make_supabase_mock(user_id=user_id, project_id=project_id, project_status="ready")
    chatbot_client.app.dependency_overrides[get_supabase_client] = lambda: supabase

    mock_generate = AsyncMock(side_effect=ValueError("No chunks found"))
    monkeypatch.setattr("app.api.chatbot.generate_rag_response", mock_generate)

    resp = chatbot_client.post(
        f"/api/chatbot/{project_id}/chat",
        json={"message": "hi", "conversation_history": []},
    )
    assert resp.status_code == 404, resp.text
    assert "no chunks" in resp.json()["detail"].lower()


def test_chatbot_rag_unexpected_error_maps_to_500(chatbot_client, monkeypatch):
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    supabase = _make_supabase_mock(user_id=user_id, project_id=project_id, project_status="ready")
    chatbot_client.app.dependency_overrides[get_supabase_client] = lambda: supabase

    mock_generate = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("app.api.chatbot.generate_rag_response", mock_generate)

    resp = chatbot_client.post(
        f"/api/chatbot/{project_id}/chat",
        json={"message": "hi", "conversation_history": []},
    )
    assert resp.status_code == 500, resp.text
    assert "failed to generate response" in resp.json()["detail"].lower()
