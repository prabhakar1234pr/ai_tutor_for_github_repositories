"""
Tests for Pattern Matcher service.
"""

from app.services.pattern_matcher import PatternMatcher


class TestPatternMatcher:
    """Test Pattern Matcher functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.matcher = PatternMatcher()

    def test_match_patterns_all_matched(self):
        """Test pattern matching when all patterns match."""
        user_code = """
import os
from typing import List

def calculate_sum(numbers: List[int]) -> int:
    return sum(numbers)

class Calculator:
    def add(self, a, b):
        return a + b
"""

        patterns = {
            "required_functions": [
                {"name": "calculate_sum", "params": ["numbers"], "return_type": "int"}
            ],
            "required_classes": [{"name": "Calculator", "methods": ["add"]}],
            "required_imports": ["os", "typing"],
            "code_patterns": [],
            "forbidden_patterns": [],
        }

        result = self.matcher.match_patterns(user_code, patterns, language="python")

        assert result["all_required_matched"]
        assert result["required_functions"]["calculate_sum"]["matched"]
        assert result["required_classes"]["Calculator"]["matched"]
        assert result["required_imports"]["os"]["matched"]

    def test_match_patterns_partial_match(self):
        """Test pattern matching when some patterns don't match."""
        user_code = """
def calculate_sum(numbers):
    return sum(numbers)
"""

        patterns = {
            "required_functions": [
                {"name": "calculate_sum", "params": ["numbers"], "return_type": "int"}
            ],
            "required_classes": [{"name": "Calculator", "methods": ["add"]}],
            "required_imports": ["os"],
            "code_patterns": [],
            "forbidden_patterns": [],
        }

        result = self.matcher.match_patterns(user_code, patterns, language="python")

        assert not result["all_required_matched"]
        assert result["required_functions"]["calculate_sum"]["matched"]
        assert not result["required_classes"]["Calculator"]["matched"]
        assert not result["required_imports"]["os"]["matched"]

    def test_match_patterns_none_matched(self):
        """Test pattern matching when no patterns match."""
        user_code = """
def other_function():
    pass
"""

        patterns = {
            "required_functions": [
                {"name": "calculate_sum", "params": ["numbers"], "return_type": "int"}
            ],
            "required_classes": [],
            "required_imports": [],
            "code_patterns": [],
            "forbidden_patterns": [],
        }

        result = self.matcher.match_patterns(user_code, patterns, language="python")

        assert not result["all_required_matched"]
        assert not result["required_functions"]["calculate_sum"]["matched"]

    def test_match_patterns_javascript(self):
        """Test pattern matching for JavaScript code."""
        user_code = """
import React from 'react';

function MyComponent() {
    return <div>Hello</div>;
}

class Calculator {
    add(a, b) {
        return a + b;
    }
}
"""

        patterns = {
            "required_functions": [{"name": "MyComponent", "type": "function"}],
            "required_classes": [{"name": "Calculator", "methods": ["add"]}],
            "required_imports": ["react"],
            "code_patterns": [],
            "forbidden_patterns": [],
        }

        result = self.matcher.match_patterns(user_code, patterns, language="javascript")

        assert result["required_functions"]["MyComponent"]["matched"]
        assert result["required_classes"]["Calculator"]["matched"]
