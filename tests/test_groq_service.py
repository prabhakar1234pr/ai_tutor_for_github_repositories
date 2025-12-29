from unittest.mock import Mock

import pytest


def test_groq_service_sends_model_and_messages(monkeypatch):
    from app.services.groq_service import GroqService
    import app.services.groq_service as groq_service_module

    # Ensure settings has an API key so GroqService can init
    monkeypatch.setattr(groq_service_module.settings, "groq_api_key", "test-key", raising=False)
    monkeypatch.setattr(
        groq_service_module.settings,
        "groq_model",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        raising=False,
    )

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(groq_service_module.httpx, "Client", FakeClient)

    svc = GroqService()
    out = svc.generate_response(
        user_query="hello",
        system_prompt="system",
        context="ctx",
        conversation_history=[{"role": "user", "content": "prev"}],
    )

    assert out == "ok"
    assert captured["json"]["model"] == groq_service_module.settings.groq_model
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["headers"]["Authorization"].startswith("Bearer ")


