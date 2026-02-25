"""
AST-based code validator for the execution sandbox.

Parses Python code and rejects dangerous patterns BEFORE execution.
This addresses the sandbox escape vulnerability where Python's class
introspection chain (e.g. ().__class__.__bases__[0].__subclasses__())
can be used to access os.system() and other dangerous functions.
"""

import ast
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_safe: bool
    violations: list[str] = field(default_factory=list)


# Modules the strategy code is allowed to import
ALLOWED_MODULES = {"pandas", "pd", "ta", "numpy", "np", "math", "json"}

# Attributes that must never be accessed (class introspection escape vectors)
BANNED_ATTRIBUTES = {
    "__subclasses__", "__bases__", "__mro__", "__class__",
    "__globals__", "__code__", "__closure__", "__func__",
    "__self__", "__module__", "__dict__", "__weakref__",
    "__init_subclass__", "__set_name__", "__del__",
    "__reduce__", "__reduce_ex__", "__getstate__",
    "__setstate__", "__format__", "__loader__", "__spec__",
    "__builtins__", "__import__",
}

# Names that must never appear as function calls
BANNED_CALLS = {
    "eval", "exec", "compile", "execfile", "input",
    "__import__", "breakpoint", "exit", "quit",
    "open", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir",
    "memoryview", "bytearray",
}

# Names that must not appear at all (dangerous modules)
BANNED_NAMES = {
    "os", "sys", "subprocess", "shutil", "socket", "http",
    "importlib", "ctypes", "signal", "threading", "multiprocessing",
    "pickle", "shelve", "tempfile", "pathlib", "io",
    "code", "codeop", "compileall", "py_compile",
    "webbrowser", "antigravity", "turtle",
}


class SandboxValidator(ast.NodeVisitor):
    """AST visitor that flags dangerous code patterns."""

    def __init__(self):
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES:
                self.violations.append(f"Forbidden import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root = node.module.split(".")[0]
            if root not in ALLOWED_MODULES:
                self.violations.append(f"Forbidden import from: '{node.module}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in BANNED_ATTRIBUTES:
            self.violations.append(f"Forbidden attribute access: '.{node.attr}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in BANNED_CALLS:
                self.violations.append(f"Forbidden function call: '{node.func.id}()'")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in BANNED_CALLS:
                self.violations.append(f"Forbidden method call: '.{node.func.attr}()'")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id in BANNED_NAMES:
            self.violations.append(f"Forbidden name reference: '{node.id}'")
        self.generic_visit(node)


def validate_code(code: str) -> ValidationResult:
    """
    Parse and validate Python code for sandbox safety.

    Returns a ValidationResult indicating whether the code is safe to execute
    and listing any violations found.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return ValidationResult(is_safe=False, violations=[f"SyntaxError: {e}"])

    validator = SandboxValidator()
    validator.visit(tree)

    return ValidationResult(
        is_safe=len(validator.violations) == 0,
        violations=validator.violations,
    )
