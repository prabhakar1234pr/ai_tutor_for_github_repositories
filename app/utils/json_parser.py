"""
Utility functions for parsing JSON responses from LLMs.
Handles markdown code blocks and malformed JSON.
"""

import json
import re
import logging

logger = logging.getLogger(__name__)


def parse_llm_json_response(response_text: str, expected_type: str = "object") -> dict | list:
    """
    Parse JSON from LLM response, handling markdown code blocks and extra text.
    
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
    
    # Check if response looks like code instead of JSON
    text_lower = response_text.strip().lower()
    code_indicators = [
        text_lower.startswith('python'),
        text_lower.startswith('javascript'),
        text_lower.startswith('java'),
        text_lower.startswith('def '),
        text_lower.startswith('class '),
        text_lower.startswith('function '),
        text_lower.startswith('const '),
        text_lower.startswith('let '),
        text_lower.startswith('var '),
        'def __init__' in text_lower,
        'function(' in text_lower,
    ]
    
    if any(code_indicators):
        raise ValueError(
            f"LLM returned code instead of JSON. "
            f"Expected JSON {expected_type}, but received code. "
            f"Response preview: {response_text[:200]}"
        )
    
    # Step 1: Remove markdown code blocks if present
    text = response_text.strip()
    
    if "```" in text:
        # Find JSON code block
        json_start = text.find("```json")
        if json_start == -1:
            json_start = text.find("```")
            if json_start != -1:
                json_start += 3  # Skip ```
        else:
            json_start += 7  # Skip ```json
        
        json_end = text.rfind("```")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            text = text[json_start:json_end].strip()
    
    # Step 2: Extract JSON object/array from text (in case there's extra text)
    if expected_type == "object":
        # Try to find JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
    elif expected_type == "array":
        # Try to find JSON array
        json_match = re.search(r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
    
    # Step 3: Clean up and parse
    text = text.strip()
    if not text:
        raise ValueError("Empty response after parsing. Original response: " + response_text[:500])
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try one more time with more aggressive cleaning
        try:
            if expected_type == "object":
                # Remove any leading/trailing non-JSON text
                cleaned = re.sub(r'^[^{]*', '', text)
                cleaned = re.sub(r'[^}]*$', '', cleaned)
            else:
                cleaned = re.sub(r'^[^\[]*', '', text)
                cleaned = re.sub(r'[^\]]*$', '', cleaned)
            
            if cleaned:
                parsed = json.loads(cleaned)
                logger.warning("⚠️  Successfully parsed JSON after aggressive cleaning")
                return parsed
            else:
                raise ValueError("Could not extract valid JSON from response")
        except Exception as parse_error:
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
                )

