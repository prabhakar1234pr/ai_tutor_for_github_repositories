"""
Markdown sanitization utilities for fixing common LLM formatting issues.
Sanitizes markdown content before saving to database.
"""

import logging
import re

logger = logging.getLogger(__name__)


def sanitize_markdown_content(content: str) -> str:
    """
    Sanitize markdown content to fix common LLM formatting issues.

    Fixes:
    - Multiple backticks around inline code (e.g., ```name``` → `name`)
    - Consecutive inline code without proper spacing
    - Dangling backticks

    Args:
        content: Raw markdown content from LLM

    Returns:
        Sanitized markdown content
    """
    if not content:
        return ""

    # Split by lines to process each line
    lines = content.split("\n")
    in_code_block = False
    result = []

    for line in lines:
        # Check if this line starts/ends a code block (``` at start of line)
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            result.append(line)
            continue

        # If we're inside a code block, don't modify
        if in_code_block:
            result.append(line)
            continue

        # Fix malformed inline code from LLM
        sanitized_line = line

        # Step 1: Normalize all sequences of 2+ backticks to a single backtick
        sanitized_line = re.sub(r"`{2,}", "`", sanitized_line)

        # Step 2: Fix consecutive inline code that runs together
        # Pattern: `word`word` → `word` `word`
        prev_line = ""
        while prev_line != sanitized_line:
            prev_line = sanitized_line
            sanitized_line = re.sub(r"`([^`\s]+)`([^`\s]+)`", r"`\1` `\2`", sanitized_line)

        # Step 3: Handle dangling backticks - word followed by backtick at end without opening
        # e.g., "use setState`" → "use `setState`"
        sanitized_line = re.sub(r"(\s)([A-Za-z_]\w*)`(?!\w)", r"\1`\2`", sanitized_line)

        # Step 4: Handle leading backtick without closing
        # e.g., "`setState is" → "`setState` is"
        sanitized_line = re.sub(r"`([A-Za-z_]\w*)(\s)", r"`\1`\2", sanitized_line)

        result.append(sanitized_line)

    sanitized_content = "\n".join(result)

    # Log if content was modified
    if sanitized_content != content:
        logger.debug("📝 Sanitized markdown content (fixed backtick formatting)")

    return sanitized_content
