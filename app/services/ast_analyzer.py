"""
AST Analyzer Service
Provides deterministic code structure analysis using AST parsing.
"""

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ASTAnalyzer:
    """
    Analyzes code structure using AST parsing.
    Provides deterministic checks for functions, classes, imports, etc.
    """

    def __init__(self):
        pass

    def analyze_python_code(self, code: str) -> dict[str, Any]:
        """
        Analyze Python code structure using AST.

        Args:
            code: Python source code

        Returns:
            {
                "functions": [{"name": str, "params": [str], "line": int}],
                "classes": [{"name": str, "methods": [str], "line": int}],
                "imports": [{"module": str, "names": [str]}],
                "has_syntax_errors": bool,
                "syntax_error": str | None
            }
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "functions": [],
                "classes": [],
                "imports": [],
                "has_syntax_errors": True,
                "syntax_error": str(e),
            }

        analyzer = _PythonASTVisitor()
        analyzer.visit(tree)

        return {
            "functions": analyzer.functions,
            "classes": analyzer.classes,
            "imports": analyzer.imports,
            "has_syntax_errors": False,
            "syntax_error": None,
        }

    def analyze_javascript_code(self, code: str) -> dict[str, Any]:
        """
        Analyze JavaScript/TypeScript code structure.

        Note: Full JS AST parsing requires external libraries (esprima, acorn).
        This is a simplified version that uses regex patterns for basic detection.
        For production, consider using esprima or acorn.

        Args:
            code: JavaScript/TypeScript source code

        Returns:
            {
                "functions": [{"name": str, "type": "function|arrow|method", "line": int}],
                "classes": [{"name": str, "methods": [str], "line": int}],
                "imports": [{"source": str, "names": [str]}],
                "has_syntax_errors": bool,
                "syntax_error": str | None
            }
        """
        import re

        functions = []
        classes = []
        imports = []

        # Extract function declarations (simplified regex)
        func_pattern = r"(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:\([^)]*\)\s*=>|function)|(\w+)\s*:\s*function)"
        for match in re.finditer(func_pattern, code):
            name = match.group(1) or match.group(2) or match.group(3)
            if name:
                line_num = code[: match.start()].count("\n") + 1
                functions.append({"name": name, "type": "function", "line": line_num})

        # Extract class declarations
        class_pattern = r"class\s+(\w+)"
        for match in re.finditer(class_pattern, code):
            name = match.group(1)
            line_num = code[: match.start()].count("\n") + 1
            classes.append({"name": name, "methods": [], "line": line_num})

        # Extract imports (ES6/CommonJS)
        import_pattern = r"import\s+(?:(?:\{([^}]+)\})|(\w+)|(\*))\s+from\s+['\"]([^'\"]+)['\"]"
        for match in re.finditer(import_pattern, code):
            names_str = match.group(1) or match.group(2) or match.group(3)
            source = match.group(4)
            names = [n.strip() for n in names_str.split(",")] if names_str else []
            imports.append({"source": source, "names": names})

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "has_syntax_errors": False,  # Can't detect syntax errors with regex
            "syntax_error": None,
        }

    def check_function_exists(
        self, code: str, function_name: str, language: str = "python"
    ) -> bool:
        """
        Check if a function exists in code.

        Args:
            code: Source code
            function_name: Function name to check
            language: "python" or "javascript"

        Returns:
            True if function exists
        """
        if language == "python":
            analysis = self.analyze_python_code(code)
            return any(f["name"] == function_name for f in analysis["functions"])
        elif language in ("javascript", "typescript"):
            analysis = self.analyze_javascript_code(code)
            return any(f["name"] == function_name for f in analysis["functions"])
        return False

    def check_class_exists(self, code: str, class_name: str, language: str = "python") -> bool:
        """
        Check if a class exists in code.

        Args:
            code: Source code
            class_name: Class name to check
            language: "python" or "javascript"

        Returns:
            True if class exists
        """
        if language == "python":
            analysis = self.analyze_python_code(code)
            return any(c["name"] == class_name for c in analysis["classes"])
        elif language in ("javascript", "typescript"):
            analysis = self.analyze_javascript_code(code)
            return any(c["name"] == class_name for c in analysis["classes"])
        return False

    def check_import_exists(self, code: str, module_name: str, language: str = "python") -> bool:
        """
        Check if an import exists in code.

        Args:
            code: Source code
            module_name: Module name to check
            language: "python" or "javascript"

        Returns:
            True if import exists
        """
        if language == "python":
            analysis = self.analyze_python_code(code)
            return any(module_name in imp.get("module", "") for imp in analysis["imports"])
        elif language in ("javascript", "typescript"):
            analysis = self.analyze_javascript_code(code)
            return any(module_name in imp.get("source", "") for imp in analysis["imports"])
        return False


class _PythonASTVisitor(ast.NodeVisitor):
    """AST visitor for Python code analysis."""

    def __init__(self):
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions."""
        params = [arg.arg for arg in node.args.args]
        self.functions.append(
            {
                "name": node.name,
                "params": params,
                "line": node.lineno,
            }
        )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions."""
        params = [arg.arg for arg in node.args.args]
        self.functions.append(
            {
                "name": node.name,
                "params": params,
                "line": node.lineno,
            }
        )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions."""
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(item.name)

        self.classes.append(
            {
                "name": node.name,
                "methods": methods,
                "line": node.lineno,
            }
        )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements."""
        for alias in node.names:
            self.imports.append(
                {
                    "module": alias.name,
                    "names": [alias.asname] if alias.asname else [],
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from-import statements."""
        module = node.module or ""
        names = [alias.name for alias in node.names]
        self.imports.append(
            {
                "module": module,
                "names": names,
            }
        )
        self.generic_visit(node)
