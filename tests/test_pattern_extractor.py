"""
Tests for Pattern Extractor service.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.pattern_extractor import PatternExtractor


class TestPatternExtractor:
    """Test Pattern Extractor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.extractor = PatternExtractor()

    @pytest.mark.asyncio
    async def test_extract_patterns_from_test_python(self):
        """Test pattern extraction from Python test file."""
        test_content = """
import pytest

def test_add_function():
    from calculator import add
    result = add(2, 3)
    assert result == 5

def test_subtract_function():
    from calculator import subtract
    result = subtract(5, 2)
    assert result == 3
"""

        # Mock the LLM response
        mock_response = {
            "required_functions": [
                {"name": "add", "params": ["a", "b"], "return_type": "int"},
                {"name": "subtract", "params": ["a", "b"], "return_type": "int"},
            ],
            "required_classes": [],
            "required_imports": ["calculator"],
            "code_patterns": [],
            "forbidden_patterns": [],
        }

        with patch.object(
            self.extractor.groq_service,
            "generate_response_async",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = str(mock_response).replace("'", '"')

            with patch(
                "app.utils.json_parser.parse_llm_json_response_async",
                new_callable=AsyncMock,
            ) as mock_parse:
                mock_parse.return_value = mock_response

                result = await self.extractor.extract_patterns_from_test(
                    test_file_content=test_content,
                    test_file_path="tests/test_calculator.py",
                    language="python",
                )

                assert result["success"]
                assert "patterns" in result
                assert len(result["patterns"]["required_functions"]) == 2

    @pytest.mark.asyncio
    async def test_extract_patterns_from_test_javascript(self):
        """Test pattern extraction from JavaScript test file."""
        test_content = """
const { add, subtract } = require('./calculator');

test('add function', () => {
    expect(add(2, 3)).toBe(5);
});

test('subtract function', () => {
    expect(subtract(5, 2)).toBe(3);
});
"""

        mock_response = {
            "required_functions": [
                {"name": "add", "params": ["a", "b"], "return_type": "number"},
                {"name": "subtract", "params": ["a", "b"], "return_type": "number"},
            ],
            "required_classes": [],
            "required_imports": ["./calculator"],
            "code_patterns": [],
            "forbidden_patterns": [],
        }

        with patch.object(
            self.extractor.groq_service,
            "generate_response_async",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = str(mock_response).replace("'", '"')

            with patch(
                "app.utils.json_parser.parse_llm_json_response_async",
                new_callable=AsyncMock,
            ) as mock_parse:
                mock_parse.return_value = mock_response

                result = await self.extractor.extract_patterns_from_test(
                    test_file_content=test_content,
                    test_file_path="tests/calculator.test.js",
                    language="javascript",
                )

                assert result["success"]
                assert "patterns" in result

    def test_detect_language(self):
        """Test language detection from file path."""
        assert self.extractor._detect_language("test.py") == "python"
        assert self.extractor._detect_language("test.js") == "javascript"
        assert self.extractor._detect_language("test.ts") == "typescript"
        assert self.extractor._detect_language("test.tsx") == "typescript"
        assert self.extractor._detect_language("unknown.xyz") == "python"  # default
