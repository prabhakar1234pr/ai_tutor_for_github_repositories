"""
PydanticAI helper wrappers for structured LLM outputs.

Goal: centralize model/provider configuration and ensure nodes can request
validated structured outputs (Pydantic models) from the LLM.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.groq import GroqProvider

from app.config import settings
from app.services.rate_limiter import get_rate_limiter


@lru_cache
def _google_vertex_model() -> GoogleModel:
    """
    Gemini via Vertex AI using ADC/service account credentials.
    """
    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required for Vertex AI Gemini structured outputs")
    provider = GoogleProvider(
        vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location
    )
    return GoogleModel(settings.gemini_model, provider=provider)


@lru_cache
def _google_gla_model() -> GoogleModel:
    """
    Gemini via Generative Language API (API key).
    Used when Vertex AI (project/ADC) isn't configured.
    """
    if not settings.gemini_api_key:
        raise ValueError(
            "Neither Vertex AI (GCP_PROJECT_ID/ADC) nor GEMINI_API_KEY is configured for structured outputs"
        )
    provider = GoogleProvider(api_key=settings.gemini_api_key)
    return GoogleModel(settings.gemini_model, provider=provider)


def _google_provider() -> GoogleProvider:
    """
    Return the configured Google provider for Gemini (Vertex AI preferred).
    """
    if settings.gcp_project_id:
        return GoogleProvider(
            vertexai=True, project=settings.gcp_project_id, location=settings.gcp_location
        )
    if settings.gemini_api_key:
        return GoogleProvider(api_key=settings.gemini_api_key)
    raise ValueError(
        "Neither Vertex AI (GCP_PROJECT_ID/ADC) nor GEMINI_API_KEY is configured for structured outputs"
    )


@lru_cache
def _groq_model() -> GroqModel:
    provider = GroqProvider(api_key=settings.groq_api_key)
    return GroqModel(settings.groq_model, provider=provider)


async def run_gemini_structured[T](
    *,
    user_prompt: str,
    system_prompt: str,
    output_type: type[T],
    model_settings: dict[str, Any] | None = None,
) -> T:
    """
    Run Gemini (Vertex AI) and force structured output validated against `output_type`.
    """
    # Reuse the existing rate limiter used by the rest of the Gemini pipeline.
    await get_rate_limiter().acquire()

    # Prefer Vertex AI (ADC/service account) when configured, else fall back to API key.
    try:
        model = _google_vertex_model()
    except Exception:
        model = _google_gla_model()

    agent = Agent(
        model,
        system_prompt=system_prompt,
        output_type=output_type,
        model_settings=model_settings or {},
    )
    try:
        result = await agent.run(user_prompt)
        return result.output
    except ModelHTTPError as exc:
        # If experimental model quota is exhausted, retry once with a stable model.
        model_name = getattr(exc, "model_name", "") or ""
        if exc.status_code == 429 and "exp" in model_name:
            fallback_model = "gemini-2.5-flash"
            fallback = GoogleModel(fallback_model, provider=_google_provider())
            fallback_agent = Agent(
                fallback,
                system_prompt=system_prompt,
                output_type=output_type,
                model_settings=model_settings or {},
            )
            result = await fallback_agent.run(user_prompt)
            return result.output
        raise


async def run_groq_structured[T](
    *,
    user_prompt: str,
    system_prompt: str,
    output_type: type[T],
    model_settings: dict[str, Any] | None = None,
) -> T:
    """
    Run Groq and force structured output validated against `output_type`.
    """
    agent = Agent(
        _groq_model(),
        system_prompt=system_prompt,
        output_type=output_type,
        model_settings=model_settings or {},
    )
    result = await agent.run(user_prompt)
    return result.output
