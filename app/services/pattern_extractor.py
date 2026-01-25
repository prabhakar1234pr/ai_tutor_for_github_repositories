"""
Pattern extraction service.
Extracts verification patterns from test files using LLM.
"""

import logging
from typing import Any

from app.agents.pydantic_models import VerificationPatternsModel
from app.agents.utils.pydantic_ai_client import run_groq_structured

logger = logging.getLogger(__name__)


class PatternExtractor:
    """
    Extract verification patterns from test files using LLM.
    Small, focused LLM call - much cheaper than task generation.
    """

    def __init__(self):
        # Structured output calls are created per request via pydantic-ai.
        pass

    async def extract_patterns_from_test(
        self,
        test_file_content: str,
        test_file_path: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """
        Use LLM to extract verification patterns from test file.

        This is a SEPARATE, SMALL LLM call:
        - Input: Just test file content (~500-2000 tokens)
        - Output: Pattern JSON (~200-500 tokens)
        - Total: ~700-2500 tokens (vs 10k+ for task generation)

        Args:
            test_file_content: Content of test file
            test_file_path: Path to test file
            language: Language (python, javascript, etc.)

        Returns:
            Dict with success status and patterns
        """
        # Auto-detect language if not provided
        if not language:
            language = self._detect_language(test_file_path)

        logger.info(f"Extracting patterns from test file: {test_file_path} ({language})")

        # Import prompt here to avoid circular import
        from app.agents.prompts.pattern_extraction import PATTERN_EXTRACTION_PROMPT

        # Build prompt
        prompt = PATTERN_EXTRACTION_PROMPT.format(
            language=language,
            test_file_content=test_file_content,
        )

        # Small, focused system prompt
        system_prompt = (
            "You are a code analysis expert. "
            "Extract verification patterns from test files. "
            "Return ONLY valid JSON, no markdown or extra text."
        )

        try:
            patterns_model = await run_groq_structured(
                user_prompt=prompt,
                system_prompt=system_prompt,
                output_type=VerificationPatternsModel,
            )
            patterns = patterns_model.model_dump()

            logger.info(
                f"✅ Extracted patterns: {len(patterns.get('required_functions', []))} functions, "
                f"{len(patterns.get('required_classes', []))} classes"
            )

            return {
                "success": True,
                "patterns": patterns,
                "language": language,
            }

        except Exception as e:
            logger.error(f"Failed to extract patterns: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "patterns": {},
            }

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = file_path.split(".")[-1].lower()
        mapping = {
            "py": "python",
            "js": "javascript",
            "jsx": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
        }
        return mapping.get(ext, "python")
