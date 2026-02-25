"""Tests for the AST-based code validator."""
from services.sandbox.code_validator import validate_code


def test_valid_strategy_passes():
    code = "def apply_strategy(df):\n    df['signal'] = 0\n    return df"
    result = validate_code(code)
    assert result.is_safe


def test_os_import_blocked():
    result = validate_code("import os")
    assert not result.is_safe


def test_subprocess_blocked():
    result = validate_code("import subprocess")
    assert not result.is_safe


def test_class_introspection_blocked():
    code = "x = ().__class__.__bases__[0].__subclasses__()"
    result = validate_code(code)
    assert not result.is_safe


def test_eval_blocked():
    code = "eval('1+1')"
    result = validate_code(code)
    assert not result.is_safe


def test_exec_blocked():
    code = "exec('print(1)')"
    result = validate_code(code)
    assert not result.is_safe


def test_open_blocked():
    code = "f = open('/etc/passwd')"
    result = validate_code(code)
    assert not result.is_safe


def test_numpy_import_allowed():
    code = "import numpy as np"
    result = validate_code(code)
    assert result.is_safe


def test_pandas_import_allowed():
    code = "import pandas as pd"
    result = validate_code(code)
    assert result.is_safe


def test_ta_import_allowed():
    code = "from ta.trend import MACD"
    result = validate_code(code)
    assert result.is_safe


def test_syntax_error_caught():
    code = "def foo(:"
    result = validate_code(code)
    assert not result.is_safe
    assert any("SyntaxError" in v for v in result.violations)


def test_multiple_violations():
    code = "import os\nimport subprocess\neval('x')"
    result = validate_code(code)
    assert not result.is_safe
    assert len(result.violations) >= 2


def test_empty_code_passes():
    result = validate_code("")
    assert result.is_safe


def test_getattr_blocked():
    code = "getattr(obj, 'method')"
    result = validate_code(code)
    assert not result.is_safe


def test_dunder_globals_blocked():
    code = "x.__globals__"
    result = validate_code(code)
    assert not result.is_safe
