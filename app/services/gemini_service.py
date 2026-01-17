"""
Google Gemini Service for high-quality content generation.
Used for critical content generation tasks that require better quality.
"""

import asyncio
import logging
import time

import httpx
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

# Gemini API endpoint
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
)

# Lazy singleton instance
_gemini_service_instance = None


def get_gemini_service() -> "GeminiService":
    """
    Get or create singleton GeminiService instance (lazy initialization).

    Returns:
        GeminiService: Singleton instance
    """
    global _gemini_service_instance

    if _gemini_service_instance is None:
        logger.info("🤖 Initializing GeminiService (first use)...")
        _gemini_service_instance = GeminiService()
        logger.info("✅ GeminiService ready (will reuse for future requests)")

    return _gemini_service_instance


class GeminiService:
    """Google Gemini service for high-quality content generation."""

    def __init__(self):
        """
        Initialize GeminiService with rate limiting and retry logic.
        """
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured. Please set it in your .env file.")

        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model if hasattr(settings, "gemini_model") else "gemini-pro"
        self.timeout = 180.0  # 180 seconds timeout
        self.rate_limiter = get_rate_limiter()

        logger.info("✅ GeminiService initialized")
        logger.debug(f"   Model: {self.model}")
        logger.debug(f"   Timeout: {self.timeout}s")
        logger.debug(f"   Rate limiter: {'enabled' if self.rate_limiter else 'disabled'}")

    async def generate_response_async(
        self,
        user_query: str,
        system_prompt: str,
        context: str = "",
        conversation_history: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """
        Async version with rate limiting and retry logic.

        Args:
            user_query: User's query/prompt
            system_prompt: System prompt/instructions
            context: Additional context (e.g., retrieved chunks)
            conversation_history: List of previous messages (not fully supported by Gemini API)
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate (None for model default)

        Returns:
            Generated response string
        """
        # Acquire rate limit permission
        await self.rate_limiter.acquire()

        # Additional delay for better rate limit compliance
        await asyncio.sleep(0.5)

        # Retry logic with exponential backoff
        return await self._generate_with_retry(
            user_query=user_query,
            system_prompt=system_prompt,
            context=context,
            conversation_history=conversation_history,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((ValueError, httpx.HTTPStatusError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )
    async def _generate_with_retry(
        self,
        user_query: str,
        system_prompt: str,
        context: str = "",
        conversation_history: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate response with retry logic.

        Args:
            user_query: User's query/prompt
            system_prompt: System prompt/instructions
            context: Additional context
            conversation_history: Previous messages (limited support)
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Generated response string
        """
        start_time = time.time()

        # Build prompt (Gemini uses a single prompt format)
        # Combine system prompt, context, and user query
        full_prompt_parts = []

        if system_prompt:
            full_prompt_parts.append(f"System Instructions: {system_prompt}")

        if context:
            full_prompt_parts.append(f"Context: {context}")

        if conversation_history:
            # Convert conversation history to text format
            history_text = "\n".join(
                f"{msg['role']}: {msg['content']}" for msg in conversation_history
            )
            full_prompt_parts.append(f"Previous Conversation:\n{history_text}")

        full_prompt_parts.append(f"User Query: {user_query}")

        full_prompt = "\n\n".join(full_prompt_parts)

        # Prepare request payload
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": full_prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        # Construct API URL with API key
        api_url = f"{GEMINI_API_URL}?key={self.api_key}"

        # Make API request
        headers = {
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            generated_text = result["candidates"][0]["content"]["parts"][0]["text"]

            duration = time.time() - start_time
            logger.debug(f"✅ Gemini response generated in {duration:.2f}s")

            return generated_text
