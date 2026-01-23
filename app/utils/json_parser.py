"""
Utility functions for parsing JSON responses from LLMs.
Handles markdown code blocks and malformed JSON.
Uses JSON sanitizer (GPT-OSS-120b) when main model returns markdown/code instead of JSON.
"""

import asyncio
import json
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_json_sanitizer = None


def _get_sanitizer():
    """Lazy import of JSON sanitizer."""
    global _json_sanitizer
    if _json_sanitizer is None:
        from app.services.json_sanitizer import get_json_sanitizer

        _json_sanitizer = get_json_sanitizer
    return _json_sanitizer()


def _is_markdown_or_code(response_text: str) -> bool:
    """
    Check if response looks like markdown/code instead of JSON.

    Args:
        response_text: Raw response text from LLM

    Returns:
        True if response appears to be markdown/code
    """
    text_lower = response_text.strip().lower()
    code_indicators = [
        text_lower.startswith("python"),
        text_lower.startswith("javascript"),
        text_lower.startswith("java"),
        text_lower.startswith("def "),
        text_lower.startswith("class "),
        text_lower.startswith("function "),
        text_lower.startswith("const "),
        text_lower.startswith("let "),
        text_lower.startswith("var "),
        "def __init__" in text_lower,
        "function(" in text_lower,
        text_lower.startswith("```"),  # Markdown code block
        text_lower.startswith("# "),  # Markdown header
        text_lower.startswith("## "),  # Markdown header
        "```" in text_lower and "json" not in text_lower[:50],  # Code block but not JSON
    ]
    return any(code_indicators)


def parse_llm_json_response(response_text: str, expected_type: str = "object") -> dict | list:
    """
    Parse JSON from LLM response, handling markdown code blocks and extra text.
    If response is markdown/code instead of JSON, uses JSON sanitizer (GPT-OSS-120b).

    Args:
        response_text: Raw response text from LLM
        expected_type: "object" for dict, "array" for list

    Returns:
        Parsed JSON (dict or list)

    Raises:
        ValueError: If JSON cannot be parsed
        json.JSONDecodeError: If JSON is invalid
    """
    if not response_text:
        raise ValueError("Empty response text")

    # Check if response looks like markdown/code instead of JSON
    is_markdown_or_code = _is_markdown_or_code(response_text)

    # If it's markdown/code and sanitizer is enabled, use sanitizer
    if is_markdown_or_code and settings.groq_sanitizer_enabled:
        try:
            logger.warning(
                f"⚠️  Detected markdown/code instead of JSON, using sanitizer ({settings.groq_sanitizer_model})..."
            )
            logger.debug(f"   Response preview: {response_text[:200]}...")

            sanitizer = _get_sanitizer()

            # Check if we're in async context
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in async context, but this is sync function
                    # Log warning and try basic parsing first
                    logger.warning(
                        "⚠️  Cannot use async sanitizer in sync context, attempting basic parsing..."
                    )
                    is_markdown_or_code = False  # Fall through to basic parsing
            except RuntimeError:
                # No event loop, we can create one
                parsed = asyncio.run(
                    sanitizer.sanitize_json(
                        malformed_response=response_text,
                        expected_type=expected_type,
                        original_error="Response appears to be markdown/code instead of JSON",
                    )
                )
                logger.info("✅ JSON successfully sanitized by GPT-OSS-120b")
                return parsed
        except Exception as sanitizer_error:
            logger.error(f"❌ JSON sanitization failed: {sanitizer_error}")
            # Fall through to basic parsing attempt

    # If not markdown/code, or sanitizer failed/disabled, try basic parsing

    # Step 1: Remove markdown code blocks if present (more aggressive)
    text = response_text.strip()

    # Remove ALL markdown code blocks (not just JSON ones)
    # This handles cases where LLM includes code examples before JSON
    text = re.sub(r"```[a-z]*\n.*?```", "", text, flags=re.DOTALL)

    # Also remove inline code blocks
    text = re.sub(r"`[^`]+`", "", text)

    # Remove any remaining markdown formatting
    text = re.sub(r"^\*\*.*?\*\*:\s*", "", text, flags=re.MULTILINE)

    # Clean up extra whitespace
    text = " ".join(text.split())

    # Step 2: Extract JSON object/array from text (improved regex for nested structures)
    if expected_type == "object":
        # Find JSON object with proper bracket matching
        depth = 0
        start_idx = text.find("{")
        if start_idx != -1:
            for i in range(start_idx, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[start_idx : i + 1]
                        break
    elif expected_type == "array":
        # Find JSON array with proper bracket matching
        depth = 0
        start_idx = text.find("[")
        if start_idx != -1:
            for i in range(start_idx, len(text)):
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        text = text[start_idx : i + 1]
                        break

    # Step 3: Clean up and parse
    text = text.strip()
    if not text:
        raise ValueError("Empty response after parsing. Original response: " + response_text[:500])

    # Step 3: Fix common JSON issues
    # Fix unescaped newlines in strings
    text = re.sub(r"(?<!\\)\n", "\\n", text)
    # Fix unescaped tabs
    text = re.sub(r"(?<!\\)\t", "\\t", text)
    # Fix unescaped quotes (but be careful not to break valid JSON)
    # Only fix quotes that are clearly unescaped within strings

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to fix common JSON errors
        try:
            # Fix invalid escape sequences
            # Replace invalid \escape with \\escape
            text = re.sub(r'\\(?![nrtbf"/\\u])', r"\\\\", text)

            # Try parsing again
            parsed = json.loads(text)
            logger.warning("⚠️  Successfully parsed JSON after fixing escape sequences")
            return parsed
        except json.JSONDecodeError:
            # Try one more time with more aggressive cleaning
            try:
                if expected_type == "object":
                    # Remove any leading/trailing non-JSON text
                    cleaned = re.sub(r"^[^{]*", "", text)
                    cleaned = re.sub(r"[^}]*$", "", cleaned)
                else:
                    cleaned = re.sub(r"^[^\[]*", "", text)
                    cleaned = re.sub(r"[^\]]*$", "", cleaned)

                if cleaned:
                    parsed = json.loads(cleaned)
                    logger.warning("⚠️  Successfully parsed JSON after aggressive cleaning")
                    return parsed
                else:
                    raise ValueError("Could not extract valid JSON from response")
            except Exception as parse_error:
                # If basic parsing fails and we haven't tried sanitizer yet, try it now
                if not is_markdown_or_code and settings.groq_sanitizer_enabled:
                    try:
                        logger.warning("⚠️  Basic JSON parsing failed, attempting sanitization...")
                        sanitizer = _get_sanitizer()
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                raise RuntimeError("Cannot use async in sync context")
                        except RuntimeError:
                            parsed = asyncio.run(
                                sanitizer.sanitize_json(
                                    malformed_response=response_text,
                                    expected_type=expected_type,
                                    original_error=str(e),
                                )
                            )
                            logger.info("✅ JSON successfully sanitized by GPT-OSS-120b")
                            return parsed
                    except Exception as sanitizer_error:
                        logger.error(f"❌ JSON sanitization failed: {sanitizer_error}")

                # Final error
                logger.error(f"❌ Failed to parse JSON: {e}")
                logger.error(f"   Attempted to parse: {text[:500]}")
                logger.error(f"   Original response: {response_text[:500]}")

                # Provide more helpful error message
                if "code instead of JSON" in str(parse_error):
                    raise parse_error  # Re-raise the code detection error as-is
                else:
                    raise ValueError(
                        f"Invalid JSON response from LLM: {e}. "
                        f"Expected JSON {expected_type}, but received: {text[:200]}. "
                        f"Full response preview: {response_text[:500]}"
                    ) from e


async def parse_llm_json_response_async(
    response_text: str, expected_type: str = "object"
) -> dict | list:
    """
    Async version of parse_llm_json_response that can use JSON sanitizer.
    Only uses sanitizer when response is markdown/code instead of JSON.

    Args:
        response_text: Raw response text from LLM
        expected_type: "object" for dict, "array" for list

    Returns:
        Parsed JSON (dict or list)
    """
    if not response_text:
        raise ValueError("Empty response text")

    # Check if response looks like markdown/code instead of JSON
    is_markdown_or_code = _is_markdown_or_code(response_text)

    # If it's markdown/code, use sanitizer immediately
    if is_markdown_or_code and settings.groq_sanitizer_enabled:
        try:
            logger.warning(
                f"⚠️  Detected markdown/code instead of JSON, using sanitizer ({settings.groq_sanitizer_model})..."
            )
            logger.debug(f"   Response preview: {response_text[:200]}...")

            sanitizer = _get_sanitizer()
            parsed = await sanitizer.sanitize_json(
                malformed_response=response_text,
                expected_type=expected_type,
                original_error="Response appears to be markdown/code instead of JSON",
            )
            logger.info("✅ JSON successfully sanitized by GPT-OSS-120b")
            return parsed
        except Exception as sanitizer_error:
            logger.error(f"❌ JSON sanitization failed: {sanitizer_error}")
            # Fall through to basic parsing

    # Try basic parsing (same logic as sync version)
    text = response_text.strip()

    # Check if response is just an empty markdown code block
    if re.match(r"^```[a-z]*\s*```\s*$", text, re.IGNORECASE | re.DOTALL):
        raise ValueError(
            "Empty markdown code block received. LLM returned empty JSON. "
            "Original response: " + response_text[:500]
        )

    # Remove ALL markdown code blocks (not just JSON ones)
    # But preserve content inside JSON code blocks
    if "```json" in text.lower() or "```" in text:
        # Try to extract JSON from markdown code block first
        json_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        if json_match:
            text = json_match.group(1).strip()
        else:
            # No JSON found in code block, remove all code blocks
            text = re.sub(r"```[a-z]*\n.*?```", "", text, flags=re.DOTALL)
    else:
        # No code blocks, use text as-is
        pass

    # Also remove inline code blocks (but only if we still have content)
    if text.strip():
        text = re.sub(r"`[^`]+`", "", text)

    # Remove any remaining markdown formatting
    text = re.sub(r"^\*\*.*?\*\*:\s*", "", text, flags=re.MULTILINE)

    # Clean up extra whitespace
    text = " ".join(text.split())

    # Extract JSON object/array from text
    if expected_type == "object":
        depth = 0
        start_idx = text.find("{")
        if start_idx != -1:
            for i in range(start_idx, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[start_idx : i + 1]
                        break
    elif expected_type == "array":
        depth = 0
        start_idx = text.find("[")
        if start_idx != -1:
            for i in range(start_idx, len(text)):
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        text = text[start_idx : i + 1]
                        break

    text = text.strip()
    if not text:
        raise ValueError("Empty response after parsing. Original response: " + response_text[:500])

    # Fix common JSON issues
    text = re.sub(r"(?<!\\)\n", "\\n", text)
    text = re.sub(r"(?<!\\)\t", "\\t", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to fix common JSON errors
        try:
            text = re.sub(r'\\(?![nrtbf"/\\u])', r"\\\\", text)
            parsed = json.loads(text)
            logger.warning("⚠️  Successfully parsed JSON after fixing escape sequences")
            return parsed
        except json.JSONDecodeError:
            # Try one more time with more aggressive cleaning
            try:
                if expected_type == "object":
                    cleaned = re.sub(r"^[^{]*", "", text)
                    cleaned = re.sub(r"[^}]*$", "", cleaned)
                else:
                    cleaned = re.sub(r"^[^\[]*", "", text)
                    cleaned = re.sub(r"[^\]]*$", "", cleaned)

                if cleaned:
                    parsed = json.loads(cleaned)
                    logger.warning("⚠️  Successfully parsed JSON after aggressive cleaning")
                    return parsed
                else:
                    raise ValueError("Could not extract valid JSON from response")
            except Exception:
                # If basic parsing fails, try sanitizer as fallback
                if settings.groq_sanitizer_enabled:
                    try:
                        logger.warning("⚠️  Basic JSON parsing failed, attempting sanitization...")
                        sanitizer = _get_sanitizer()
                        parsed = await sanitizer.sanitize_json(
                            malformed_response=response_text,
                            expected_type=expected_type,
                            original_error=str(e),
                        )
                        logger.info("✅ JSON successfully sanitized by GPT-OSS-120b")
                        return parsed
                    except Exception as sanitizer_error:
                        logger.error(f"❌ JSON sanitization failed: {sanitizer_error}")

                # Final error
                logger.error(f"❌ Failed to parse JSON: {e}")
                logger.error(f"   Attempted to parse: {text[:500]}")
                logger.error(f"   Original response: {response_text[:500]}")
                raise ValueError(
                    f"Invalid JSON response from LLM: {e}. "
                    f"Expected JSON {expected_type}, but received: {text[:200]}. "
                    f"Full response preview: {response_text[:500]}"
                ) from e
