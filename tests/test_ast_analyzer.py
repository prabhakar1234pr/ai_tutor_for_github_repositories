"""
Tests for AST Analyzer service.
"""

from app.services.ast_analyzer import ASTAnalyzer


class TestASTAnalyzer:
    """Test AST Analyzer functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = ASTAnalyzer()

    def test_analyze_python_code_basic(self):
        """Test basic Python code analysis."""
        code = """
def hello_world():
    print("Hello, World!")

class MyClass:
    def method(self):
        pass
"""
        result = self.analyzer.analyze_python_code(code)

        assert not result["has_syntax_errors"]
        assert len(result["functions"]) >= 1  # Includes both hello_world and method
        function_names = [f["name"] for f in result["functions"]]
        assert "hello_world" in function_names
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "MyClass"

    def test_analyze_python_code_with_imports(self):
        """Test Python code with imports."""
        code = """
import os
from typing import List, Dict

def process_data(data: List[Dict]) -> None:
    pass
"""
        result = self.analyzer.analyze_python_code(code)

        assert not result["has_syntax_errors"]
        assert len(result["imports"]) >= 1
        assert len(result["functions"]) == 1

    def test_analyze_python_code_syntax_error(self):
        """Test Python code with syntax errors."""
        code = """
def broken_function(
    # Missing closing parenthesis
"""
        result = self.analyzer.analyze_python_code(code)

        assert result["has_syntax_errors"]
        assert result["syntax_error"] is not None

    def test_check_function_exists(self):
        """Test function existence check."""
        code = """
def my_function(x, y):
    return x + y
"""
        assert self.analyzer.check_function_exists(code, "my_function", "python")
        assert not self.analyzer.check_function_exists(code, "nonexistent", "python")

    def test_check_class_exists(self):
        """Test class existence check."""
        code = """
class MyClass:
    pass
"""
        assert self.analyzer.check_class_exists(code, "MyClass", "python")
        assert not self.analyzer.check_class_exists(code, "Nonexistent", "python")

    def test_check_import_exists(self):
        """Test import existence check."""
        code = """
import os
from typing import List
"""
        assert self.analyzer.check_import_exists(code, "os", "python")
        assert self.analyzer.check_import_exists(code, "typing", "python")
        assert not self.analyzer.check_import_exists(code, "nonexistent", "python")

    def test_analyze_javascript_code_basic(self):
        """Test basic JavaScript code analysis."""
        code = """
function helloWorld() {
    console.log("Hello");
}

class MyClass {
    method() {
        return true;
    }
}
"""
        result = self.analyzer.analyze_javascript_code(code)

        assert len(result["functions"]) >= 1
        assert len(result["classes"]) >= 1

    def test_analyze_javascript_code_with_imports(self):
        """Test JavaScript code with imports."""
        code = """
import React from 'react';
import { useState } from 'react';

function Component() {
    return null;
}
"""
        result = self.analyzer.analyze_javascript_code(code)

        assert len(result["imports"]) >= 1
        assert len(result["functions"]) >= 1
