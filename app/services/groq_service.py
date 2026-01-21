import asyncio
import json
import logging
import time
from typing import Any

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

# Groq API endpoint (OpenAI-compatible)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Lazy singleton instances
_groq_service_instance = None
_groq_verification_service_instance = None


def get_groq_service() -> "GroqService":
    """
    Get or create singleton GroqService instance (lazy initialization).

    Returns:
        GroqService: Singleton instance
    """
    global _groq_service_instance

    if _groq_service_instance is None:
        logger.info("🤖 Initializing GroqService (first use)...")
        logger.info(f"   Model: {settings.groq_model}")
        _groq_service_instance = GroqService()
        logger.info("✅ GroqService ready (will reuse for future requests)")

    return _groq_service_instance


def get_groq_verification_service() -> "GroqService":
    """
    Get or create singleton GroqService instance for task verification (uses GROQ_API_KEY2).

    Returns:
        GroqService: Singleton instance with GROQ_API_KEY2
    """
    global _groq_verification_service_instance

    if _groq_verification_service_instance is None:
        logger.info("🤖 Initializing GroqService for verification (first use)...")
        logger.info(f"   Model: {settings.groq_model}")
        _groq_verification_service_instance = GroqService(use_api_key2=True)
        logger.info("✅ GroqService for verification ready (will reuse for future requests)")

    return _groq_verification_service_instance


class GroqService:
    def __init__(self, use_api_key2: bool = False):
        """
        Initialize GroqService with rate limiting and retry logic.

        Args:
            use_api_key2: If True, use GROQ_API_KEY2 (for verification with higher limits)
        """
        if use_api_key2:
            if not settings.groq_api_key2:
                raise ValueError(
                    "GROQ_API_KEY2 is not configured. Please set it in your .env file."
                )
            self.api_key = settings.groq_api_key2
        else:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is not configured. Please set it in your .env file.")
            self.api_key = settings.groq_api_key

        self.model = settings.groq_model
        self.api_url = GROQ_API_URL
        self.timeout = 180.0  # 180 seconds timeout (longer for agent workflows)
        self.rate_limiter = get_rate_limiter()

        logger.info("✅ GroqService initialized")
        logger.debug(f"   API URL: {self.api_url}")
        logger.debug(f"   Model: {self.model}")
        logger.debug(f"   Timeout: {self.timeout}s")
        logger.debug(f"   Rate limiter: {'enabled' if self.rate_limiter else 'disabled'}")

    async def generate_response_async(
        self,
        user_query: str,
        system_prompt: str,
        context: str,
        conversation_history: list[dict] | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        Async version with rate limiting and retry logic.

        Args:
            user_query: User's query
            system_prompt: System prompt
            context: Additional context
            conversation_history: Conversation history
            temperature: LLM temperature (0.0-2.0, None uses default 0.7)
        """
        # Acquire rate limit permission (includes minimum delay)
        await self.rate_limiter.acquire()

        # Additional delay for better rate limit compliance
        # This ensures we don't hit limits even with burst requests
        await asyncio.sleep(0.5)  # 500ms additional buffer

        # Retry logic with exponential backoff
        return await self._generate_with_retry(
            user_query=user_query,
            system_prompt=system_prompt,
            context=context,
            conversation_history=conversation_history,
            temperature=temperature,
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
        context: str,
        conversation_history: list[dict] | None = None,
        temperature: float | None = None,
    ) -> str:
        """Internal method with retry logic"""
        return await self._make_api_request(
            user_query=user_query,
            system_prompt=system_prompt,
            context=context,
            conversation_history=conversation_history,
            temperature=temperature,
        )

    async def _make_api_request(
        self,
        user_query: str,
        system_prompt: str,
        context: str,
        conversation_history: list[dict] | None = None,
        temperature: float | None = None,
    ) -> str:
        """Make the actual API request"""
        if conversation_history is None:
            conversation_history = []

        start_time = time.time()
        logger.info(f"🤖 Generating response with Groq API (model: {self.model})")
        logger.debug(f"   User query length: {len(user_query)} chars")
        logger.debug(f"   Context length: {len(context)} chars")
        logger.debug(f"   Conversation history: {len(conversation_history)} messages")

        # Build messages array for Groq API
        messages = []

        # Add system prompt
        messages.append({"role": "system", "content": system_prompt})

        # Add context as a system message (or user message)
        if context:
            context_message = (
                f"Here is the relevant context from the codebase:\n\n{context}\n\n"
                f"Please answer the user's question based on this context. "
                f"If the answer cannot be found in the context, say so."
            )
            messages.append({"role": "system", "content": context_message})

        # Add conversation history
        for msg in conversation_history:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current user query
        messages.append({"role": "user", "content": user_query})

        # Prepare API request
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else 0.7,
            "max_tokens": 2000,
            "top_p": 1.0,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(
            f"   Request payload: model={self.model}, messages={len(messages)}, max_tokens={payload['max_tokens']}, temperature={payload['temperature']}"
        )

        # Make API request (async)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.api_url,
                json=payload,
                headers=headers,
            )

            # Handle rate limit errors specifically
            if response.status_code == 429:
                error_detail = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_msg = error_detail.get("error", {}).get("message", "Rate limit exceeded")

                # Extract retry-after if available
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    wait_time = float(retry_after) + 1
                    logger.warning(
                        f"⏳ Rate limited, waiting {wait_time}s as per Retry-After header"
                    )
                    await asyncio.sleep(wait_time)
                    # Retry once more after waiting
                    response = await client.post(
                        self.api_url,
                        json=payload,
                        headers=headers,
                    )
                else:
                    raise ValueError(
                        f"Groq API HTTP error: 429 - Rate limit exceeded - {error_msg}"
                    )

            response.raise_for_status()

            result = response.json()

            # Extract response text
            if "choices" not in result or len(result["choices"]) == 0:
                raise ValueError("No choices returned from Groq API")

            assistant_message = result["choices"][0]["message"]["content"]

            # Log usage info if available
            if "usage" in result:
                usage = result["usage"]
                logger.debug(
                    f"   Token usage: prompt={usage.get('prompt_tokens', 0)}, "
                    f"completion={usage.get('completion_tokens', 0)}, "
                    f"total={usage.get('total_tokens', 0)}"
                )

            duration = time.time() - start_time
            logger.info(
                f"✅ Generated response ({len(assistant_message)} chars) in {duration:.3f}s"
            )

            return assistant_message

    async def generate_with_tools_async(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """
        Generate response with function calling support (OpenAI-compatible format).

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            tools: List of tool/function definitions (OpenAI format)
            temperature: LLM temperature (0.0-2.0, default 0.0 for deterministic)
            max_tokens: Maximum tokens in response (default 4000 for agent workflows)

        Returns:
            {
                "content": str | None,  # Text content if no tool calls
                "tool_calls": list[dict] | None,  # Tool calls if agent wants to call tools
                "finish_reason": str,  # "stop", "tool_calls", etc.
                "usage": dict | None  # Token usage info
            }
        """
        # Acquire rate limit permission
        await self.rate_limiter.acquire()

        # Additional delay for rate limit compliance
        await asyncio.sleep(0.5)

        # Retry logic with exponential backoff
        return await self._generate_with_tools_retry(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @retry(
        stop=stop_after_attempt(5),  # More attempts for rate limits
        wait=wait_exponential(multiplier=2, min=5, max=120),  # Longer waits: 5s, 10s, 20s, 40s, 80s
        retry=retry_if_exception_type((ValueError, httpx.HTTPStatusError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True,
    )
    async def _generate_with_tools_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """Internal method with retry logic"""
        return await self._make_tools_api_request(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _make_tools_api_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """
        Make the actual API request to Groq with function calling support.

        Args:
            messages: List of message dicts
            tools: List of tool definitions (OpenAI function calling format)
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Response dict with content, tool_calls, finish_reason, usage
        """
        start_time = time.time()
        logger.info(f"🤖 Calling Groq API with tools (model: {self.model})")
        logger.debug(f"   Messages: {len(messages)}")
        logger.debug(f"   Tools: {len(tools) if tools else 0}")
        logger.debug(f"   Temperature: {temperature}, Max tokens: {max_tokens}")

        # Prepare API request payload
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add tools if provided (OpenAI-compatible format)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"  # Let model decide when to call tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Calculate approximate request size
        payload_size = len(json.dumps(payload))
        logger.info(f"   Request size: ~{payload_size / 1024:.1f} KB")
        logger.debug(f"   API URL: {self.api_url}")

        # Make API request (async)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                )

                # Handle rate limit errors specifically
                if response.status_code == 429:
                    error_detail = (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    error_msg = error_detail.get("error", {}).get("message", "Rate limit exceeded")

                    # Extract retry-after if available
                    retry_after = response.headers.get("retry-after")
                    if retry_after:
                        wait_time = float(retry_after) + 2  # Add buffer
                        logger.warning(
                            f"⏳ Rate limited, waiting {wait_time}s as per Retry-After header"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        # No Retry-After header - wait longer (60 seconds for free tier)
                        wait_time = 60.0
                        logger.warning(
                            f"⏳ Rate limited (no Retry-After header), waiting {wait_time}s before retry"
                        )
                        await asyncio.sleep(wait_time)

                    # Raise error to trigger retry logic with exponential backoff
                    raise ValueError(
                        f"Groq API HTTP error: 429 - Rate limit exceeded - {error_msg}"
                    )

                response.raise_for_status()

                result = response.json()

                # Extract response
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("No choices returned from Groq API")

                choice = result["choices"][0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "stop")

                # Extract content (if present)
                content = message.get("content")

                # Extract tool calls (if present)
                tool_calls = message.get("tool_calls")

                # Extract usage info
                usage = result.get("usage")

                # Log usage info if available
                if usage:
                    logger.debug(
                        f"   Token usage: prompt={usage.get('prompt_tokens', 0)}, "
                        f"completion={usage.get('completion_tokens', 0)}, "
                        f"total={usage.get('total_tokens', 0)}"
                    )

                duration = time.time() - start_time
                logger.info(
                    f"✅ Groq response generated in {duration:.3f}s "
                    f"(finish_reason: {finish_reason}, tool_calls: {len(tool_calls) if tool_calls else 0})"
                )

                return {
                    "content": content,
                    "tool_calls": tool_calls,
                    "finish_reason": finish_reason,
                    "usage": usage,
                }
        except httpx.TimeoutException as err:
            logger.error(f"❌ Request timed out after {self.timeout}s")
            logger.error(f"   URL: {self.api_url}")
            logger.error(f"   Request size: ~{payload_size / 1024:.1f} KB")
            logger.error(
                f"   Possible causes: 1) API slow/down, 2) Request too large ({payload_size / 1024:.1f} KB), 3) Network issues, 4) Invalid API key"
            )
            raise ValueError(
                f"Groq API request timed out after {self.timeout}s. Check API status and request size."
            ) from err
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("❌ Authentication failed - API key may be invalid")
                logger.error("   Check your GROQ_API_KEY2 in .env file")
            raise

    def generate_response(
        self,
        user_query: str,
        system_prompt: str,
        context: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """
        Generate a response using Groq API with RAG context.

        Args:
            user_query: The user's question
            system_prompt: System instructions for the AI
            context: Retrieved chunks from codebase as context
            conversation_history: Previous messages [{"role": "user|assistant", "content": "..."}]

        Returns:
            Generated response string

        Raises:
            ValueError: If API key is missing or invalid
            httpx.HTTPError: If API request fails
        """
        if conversation_history is None:
            conversation_history = []

        logger.info(f"🤖 Generating response with Groq API (model: {self.model})")
        logger.debug(f"   User query length: {len(user_query)} chars")
        logger.debug(f"   Context length: {len(context)} chars")
        logger.debug(f"   Conversation history: {len(conversation_history)} messages")

        # Build messages array for Groq API
        messages = []

        # Add system prompt
        messages.append({"role": "system", "content": system_prompt})

        # Add context as a system message (or user message)
        if context:
            context_message = (
                f"Here is the relevant context from the codebase:\n\n{context}\n\n"
                f"Please answer the user's question based on this context. "
                f"If the answer cannot be found in the context, say so."
            )
            messages.append({"role": "system", "content": context_message})

        # Add conversation history
        for msg in conversation_history:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current user query
        messages.append({"role": "user", "content": user_query})

        # Prepare API request
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 1.0,
        }

        logger.debug(
            f"   Request payload: model={self.model}, messages={len(messages)}, max_tokens={payload['max_tokens']}"
        )

        """
        Synchronous wrapper for generate_response (for backward compatibility).
        Uses async implementation with event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, we can't use sync wrapper
                # This should not happen - caller should use async version
                raise RuntimeError(
                    "Cannot use sync generate_response in async context. "
                    "Use generate_response_async instead."
                )
            else:
                # Run async version in event loop
                return loop.run_until_complete(
                    self.generate_response_async(
                        user_query=user_query,
                        system_prompt=system_prompt,
                        context=context,
                        conversation_history=conversation_history,
                    )
                )
        except RuntimeError:
            # No event loop, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.generate_response_async(
                        user_query=user_query,
                        system_prompt=system_prompt,
                        context=context,
                        conversation_history=conversation_history,
                    )
                )
            finally:
                loop.close()

        except httpx.HTTPStatusError as e:
            error_msg = f"Groq API HTTP error: {e.response.status_code}"
            if e.response.status_code == 401:
                error_msg += " - Invalid API key"
            elif e.response.status_code == 429:
                error_msg += " - Rate limit exceeded"
            elif e.response.status_code == 500:
                error_msg += " - Groq API server error"

            try:
                error_detail = e.response.json()
                if "error" in error_detail:
                    error_msg += f" - {error_detail['error'].get('message', '')}"
            except Exception:
                error_msg += f" - {e.response.text[:200]}"

            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg) from e

        except httpx.TimeoutException as e:
            error_msg = f"Groq API request timed out after {self.timeout}s"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg) from e

        except httpx.RequestError as e:
            error_msg = f"Groq API request failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected error calling Groq API: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            raise ValueError(error_msg) from e
