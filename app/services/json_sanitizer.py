"""
JSON Sanitizer Service using Groq's GPT-OSS-120b model.
Only used when main agent model returns markdown/code instead of JSON.
"""

import logging
import asyncio
import json
from typing import Optional
from app.config import settings
from app.services.groq_service import GROQ_API_URL, get_rate_limiter
import httpx

logger = logging.getLogger(__name__)

# Lazy singleton instance
_json_sanitizer_instance = None


def get_json_sanitizer() -> 'JsonSanitizer':
    """
    Get or create singleton JsonSanitizer instance.
    
    Returns:
        JsonSanitizer: Singleton instance
    """
    global _json_sanitizer_instance
    
    if _json_sanitizer_instance is None:
        logger.info("🔧 Initializing JsonSanitizer (first use)...")
        logger.info(f"   Model: {settings.groq_sanitizer_model}")
        _json_sanitizer_instance = JsonSanitizer()
        logger.info("✅ JsonSanitizer ready")
    
    return _json_sanitizer_instance


class JsonSanitizer:
    """
    Service to sanitize and fix malformed JSON using Groq's GPT-OSS-120b model.
    Only used when main agent model returns markdown/code instead of JSON.
    """
    
    def __init__(self):
        """Initialize JsonSanitizer with Groq API."""
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not configured. Please set it in your .env file."
            )
        
        self.api_key = settings.groq_api_key
        self.model = settings.groq_sanitizer_model  # e.g., "gpt-oss-120b"
        self.api_url = GROQ_API_URL  # Same Groq endpoint
        self.timeout = httpx.Timeout(60.0, connect=10.0)
        self.rate_limiter = get_rate_limiter()  # Reuse same rate limiter
    
    async def sanitize_json(
        self,
        malformed_response: str,
        expected_type: str = "object",
        original_error: Optional[str] = None
    ) -> dict | list:
        """
        Sanitize malformed JSON (markdown/code) using Groq's GPT-OSS-120b model.
        
        Args:
            malformed_response: The malformed response (markdown/code) to convert to JSON
            expected_type: "object" for dict, "array" for list
            original_error: Optional error message from initial parse attempt
            
        Returns:
            Parsed JSON (dict or list)
            
        Raises:
            ValueError: If JSON cannot be sanitized
        """
        logger.info(f"🔧 Sanitizing JSON using {self.model} (expected_type={expected_type})...")
        logger.debug(f"   Malformed response preview: {malformed_response[:200]}...")
        
        # Acquire rate limit permission (reuse same rate limiter)
        await self.rate_limiter.acquire()
        await asyncio.sleep(0.5)  # Additional buffer
        
        # Create prompt for sanitization
        system_prompt = (
            "You are a JSON conversion expert. Your ONLY job is to convert markdown/code "
            "responses into valid JSON. Return ONLY valid JSON. Do NOT add any explanation, "
            "comments, or markdown code blocks. Return ONLY the JSON. "
            "CRITICAL: Preserve ALL fields from the original response, especially the 'content' field. "
            "Do NOT omit, truncate, or skip any fields."
        )
        
        # For content generation, we need to preserve the full response
        # Content can be 1500-2500 words, which when escaped can be 10k+ chars
        # Use a much larger limit, but still cap at reasonable size to avoid API limits
        max_input_length = 16000  # Increased from 4000 to handle large content fields
        
        user_prompt = f"""Convert this response to valid JSON {expected_type}. The response may be in markdown, code, or other format. Extract the data and return ONLY valid JSON.

**Expected Type:** {expected_type} ({'object/dict' if expected_type == 'object' else 'array/list'})

**Response to Convert:**
{malformed_response[:max_input_length]}

{f'**Original Error:** {original_error}' if original_error else ''}

**CRITICAL RULES:**
1. Return ONLY the fixed JSON - no markdown code blocks (no ```json or ```)
2. Start with {{ if object, [ if array
3. End with }} if object, ] if array
4. Properly escape all special characters (newlines as \\n, quotes as \\")
5. Ensure all strings use double quotes
6. Fix any syntax errors (missing commas, brackets, etc.)
7. **PRESERVE ALL DATA** - extract ALL relevant information from the response, especially the "content" field if present
8. If the content contains markdown or code examples, properly escape them in JSON strings
9. **DO NOT OMIT OR TRUNCATE ANY FIELDS** - ensure all fields from the original response are included in the JSON
10. If the response contains a "content" field, preserve it completely - do not truncate or omit it

**Return ONLY the fixed JSON, nothing else.**"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,  # Low temperature for consistent JSON output
            "max_tokens": 16000,  # Increased to handle large content fields (1500-2500 words when escaped)
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Extract content from response
                sanitized_json_text = result["choices"][0]["message"]["content"].strip()
                
                logger.debug(f"   Sanitized JSON preview: {sanitized_json_text[:200]}...")
                
                # Remove markdown code blocks if present (defensive)
                if sanitized_json_text.startswith("```"):
                    start_idx = sanitized_json_text.find("```") + 3
                    if sanitized_json_text[start_idx:start_idx+5] == "json":
                        start_idx += 5
                    end_idx = sanitized_json_text.rfind("```")
                    sanitized_json_text = sanitized_json_text[start_idx:end_idx].strip()
                
                # Parse the sanitized JSON
                try:
                    parsed = json.loads(sanitized_json_text)
                    
                    # Validate type
                    if expected_type == "object" and not isinstance(parsed, dict):
                        raise ValueError(f"Expected dict, got {type(parsed).__name__}")
                    elif expected_type == "array" and not isinstance(parsed, list):
                        raise ValueError(f"Expected list, got {type(parsed).__name__}")
                    
                    logger.info(f"✅ Successfully sanitized JSON ({expected_type}) using {self.model}")
                    return parsed
                    
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Sanitized JSON still invalid: {e}")
                    logger.error(f"   Sanitized text: {sanitized_json_text[:500]}")
                    raise ValueError(f"Sanitizer returned invalid JSON: {e}")
                    
        except httpx.HTTPStatusError as e:
            error_msg = f"Groq API HTTP error: {e.response.status_code}"
            try:
                error_detail = e.response.json()
                if "error" in error_detail:
                    error_msg += f" - {error_detail['error'].get('message', '')}"
            except:
                pass
            logger.error(f"❌ JSON sanitization failed: {error_msg}")
            raise ValueError(f"JSON sanitization failed: {error_msg}")
        
        except Exception as e:
            logger.error(f"❌ JSON sanitization failed: {e}", exc_info=True)
            raise ValueError(f"JSON sanitization failed: {e}")

