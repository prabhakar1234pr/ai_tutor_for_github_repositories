"""
Azure OpenAI Service for high-quality content generation.
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

# Lazy singleton instance
_azure_openai_service_instance = None


def get_azure_openai_service() -> "AzureOpenAIService":
    """
    Get or create singleton AzureOpenAIService instance (lazy initialization).

    Returns:
        AzureOpenAIService: Singleton instance
    """
    global _azure_openai_service_instance

    if _azure_openai_service_instance is None:
        logger.info("🤖 Initializing AzureOpenAIService (first use)...")
        logger.info(f"   Deployment: {settings.azure_openai_deployment_gpt_4_1}")
        _azure_openai_service_instance = AzureOpenAIService()
        logger.info("✅ AzureOpenAIService ready (will reuse for future requests)")

    return _azure_openai_service_instance


class AzureOpenAIService:
    """Azure OpenAI service for high-quality content generation."""

    def __init__(self):
        """
        Initialize AzureOpenAIService with rate limiting and retry logic.
        """
        if not settings.azure_openai_key:
            raise ValueError("AZURE_OPENAI_KEY is not configured. Please set it in your .env file.")
        if not settings.azure_openai_endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT is not configured. Please set it in your .env file."
            )
        if not settings.azure_openai_deployment_gpt_4_1:
            raise ValueError(
                "AZURE_OPENAI_DEPLOYMENT_GPT_4_1 is not configured. Please set it in your .env file."
            )

        self.api_key = settings.azure_openai_key
        self.endpoint = settings.azure_openai_endpoint.rstrip("/")
        self.deployment = settings.azure_openai_deployment_gpt_4_1
        self.api_version = settings.azure_openai_api_version
        self.timeout = settings.azure_openai_timeout
        self.rate_limiter = get_rate_limiter()

        # Construct API URL
        self.api_url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"

        logger.info("✅ AzureOpenAIService initialized")
        logger.debug(f"   API URL: {self.api_url}")
        logger.debug(f"   Deployment: {self.deployment}")
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
            conversation_history: List of previous messages [{"role": "user|assistant", "content": "..."}]
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
            conversation_history: Previous messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Generated response string
        """
        start_time = time.time()

        # Build messages
        messages = []

        # Add system prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # Add context if provided
        if context:
            user_query_with_context = f"{context}\n\n{user_query}"
        else:
            user_query_with_context = user_query

        # Add current user query
        messages.append({"role": "user", "content": user_query_with_context})

        # Prepare request payload
        payload = {
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        # Make API request
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.api_url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            generated_text = result["choices"][0]["message"]["content"]

            duration = time.time() - start_time
            logger.debug(f"✅ Azure OpenAI response generated in {duration:.2f}s")

            return generated_text
