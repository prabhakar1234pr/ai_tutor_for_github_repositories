"""
Pattern Matcher Service
Matches user code against extracted verification patterns using AST analysis.
"""

import logging
from typing import Any

from app.services.ast_analyzer import ASTAnalyzer

logger = logging.getLogger(__name__)


class PatternMatcher:
    """
    Matches user code against verification patterns extracted from test files.
    Uses AST analysis for deterministic pattern matching.
    """

    def __init__(self):
        self.ast_analyzer = ASTAnalyzer()

    def match_patterns(
        self, user_code: str, patterns: dict[str, Any], language: str = "python"
    ) -> dict[str, Any]:
        """
        Match user code against verification patterns.

        Args:
            user_code: User's code to check
            patterns: Patterns extracted from test file (from PatternExtractor)
            language: "python" or "javascript"

        Returns:
            {
                "required_functions": {
                    "function_name": {"exists": bool, "matched": bool}
                },
                "required_classes": {
                    "class_name": {"exists": bool, "matched": bool}
                },
                "required_imports": {
                    "module_name": {"exists": bool, "matched": bool}
                },
                "code_patterns": {
                    "pattern_type": {"matched": bool, "details": str}
                },
                "all_required_matched": bool
            }
        """
        results = {
            "required_functions": {},
            "required_classes": {},
            "required_imports": {},
            "code_patterns": {},
            "all_required_matched": True,
        }

        # Check required functions
        required_functions = patterns.get("required_functions", [])
        for func_pattern in required_functions:
            func_name = func_pattern.get("name", "")
            if func_name:
                exists = self.ast_analyzer.check_function_exists(user_code, func_name, language)
                results["required_functions"][func_name] = {
                    "exists": exists,
                    "matched": exists,
                }
                if not exists:
                    results["all_required_matched"] = False

        # Check required classes
        required_classes = patterns.get("required_classes", [])
        for class_pattern in required_classes:
            class_name = class_pattern.get("name", "")
            if class_name:
                exists = self.ast_analyzer.check_class_exists(user_code, class_name, language)
                results["required_classes"][class_name] = {
                    "exists": exists,
                    "matched": exists,
                }
                if not exists:
                    results["all_required_matched"] = False

        # Check required imports
        required_imports = patterns.get("required_imports", [])
        for import_name in required_imports:
            exists = self.ast_analyzer.check_import_exists(user_code, import_name, language)
            results["required_imports"][import_name] = {
                "exists": exists,
                "matched": exists,
            }
            if not exists:
                results["all_required_matched"] = False

        # Check code patterns (simplified - can be enhanced)
        code_patterns = patterns.get("code_patterns", [])
        for pattern in code_patterns:
            pattern_type = pattern.get("type", "")
            pattern_desc = pattern.get("description", "")
            # Basic pattern matching (can be enhanced with regex or more sophisticated checks)
            matched = pattern_desc.lower() in user_code.lower() if pattern_desc else False
            results["code_patterns"][pattern_type] = {
                "matched": matched,
                "details": pattern_desc,
            }
            if not matched:
                results["all_required_matched"] = False

        return results
