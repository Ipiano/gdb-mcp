"""Unit tests for MCP server."""

import pytest
from pydantic import ValidationError
from gdb_mcp.server import (
    StartSessionArgs,
    ExecuteCommandArgs,
    GetBacktraceArgs,
    SetBreakpointArgs,
    EvaluateExpressionArgs,
    GetVariablesArgs,
)


class TestStartSessionArgs:
    """Test cases for StartSessionArgs model."""

    def test_minimal_args(self):
        """Test creating StartSessionArgs with minimal arguments."""
        args = StartSessionArgs()
        assert args.program is None
        assert args.args is None
        assert args.init_commands is None
        assert args.env is None
        assert (
            args.gdb_path is None
        )  # Default to None, actual default determined by GDB_PATH env var or "gdb"

    def test_full_args(self):
        """Test creating StartSessionArgs with all arguments."""
        args = StartSessionArgs(
            program="/bin/ls",
            args=["-la", "/tmp"],
            init_commands=["set pagination off"],
            env={"DEBUG": "1"},
            gdb_path="/usr/local/bin/gdb",
        )

        assert args.program == "/bin/ls"
        assert args.args == ["-la", "/tmp"]
        assert args.init_commands == ["set pagination off"]
        assert args.env == {"DEBUG": "1"}
        assert args.gdb_path == "/usr/local/bin/gdb"

    def test_env_dict_validation(self):
        """Test that env accepts dictionary of strings."""
        args = StartSessionArgs(program="/bin/ls", env={"VAR1": "value1", "VAR2": "value2"})

        assert args.env == {"VAR1": "value1", "VAR2": "value2"}


class TestExecuteCommandArgs:
    """Test cases for ExecuteCommandArgs model."""

    def test_command_required(self):
        """Test that command is required."""
        with pytest.raises(ValidationError):
            ExecuteCommandArgs()

    def test_command_arg(self):
        """Test command argument."""
        args = ExecuteCommandArgs(command="info threads")
        assert args.command == "info threads"


class TestGetBacktraceArgs:
    """Test cases for GetBacktraceArgs model."""

    def test_defaults(self):
        """Test default values."""
        args = GetBacktraceArgs()
        assert args.thread_id is None
        assert args.max_frames == 100

    def test_with_thread_id(self):
        """Test with specific thread ID."""
        args = GetBacktraceArgs(thread_id=5, max_frames=50)
        assert args.thread_id == 5
        assert args.max_frames == 50


class TestSetBreakpointArgs:
    """Test cases for SetBreakpointArgs model."""

    def test_location_required(self):
        """Test that location is required."""
        with pytest.raises(ValidationError):
            SetBreakpointArgs()

    def test_minimal_breakpoint(self):
        """Test minimal breakpoint (just location)."""
        args = SetBreakpointArgs(location="main")
        assert args.location == "main"
        assert args.condition is None
        assert args.temporary is False

    def test_conditional_breakpoint(self):
        """Test conditional breakpoint."""
        args = SetBreakpointArgs(location="foo.c:42", condition="x > 10", temporary=True)
        assert args.location == "foo.c:42"
        assert args.condition == "x > 10"
        assert args.temporary is True


class TestEvaluateExpressionArgs:
    """Test cases for EvaluateExpressionArgs model."""

    def test_expression_required(self):
        """Test that expression is required."""
        with pytest.raises(ValidationError):
            EvaluateExpressionArgs()

    def test_expression(self):
        """Test with expression."""
        args = EvaluateExpressionArgs(expression="x + y")
        assert args.expression == "x + y"


class TestGetVariablesArgs:
    """Test cases for GetVariablesArgs model."""

    def test_defaults(self):
        """Test default values."""
        args = GetVariablesArgs()
        assert args.thread_id is None
        assert args.frame == 0

    def test_with_values(self):
        """Test with specific values."""
        args = GetVariablesArgs(thread_id=3, frame=2)
        assert args.thread_id == 3
        assert args.frame == 2


class TestExecuteShellArgs:
    """Test cases for ExecuteShellArgs model."""

    def test_command_required(self):
        """Test that command is required."""
        from gdb_mcp.server import ExecuteShellArgs

        with pytest.raises(ValidationError):
            ExecuteShellArgs()

    def test_command_arg(self):
        """Test command argument."""
        from gdb_mcp.server import ExecuteShellArgs

        args = ExecuteShellArgs(command="ls -la")
        assert args.command == "ls -la"


class TestExecutePythonArgs:
    """Test cases for ExecutePythonArgs model."""

    def test_code_required(self):
        """Test that code is required."""
        from gdb_mcp.server import ExecutePythonArgs

        with pytest.raises(ValidationError):
            ExecutePythonArgs()

    def test_code_arg(self):
        """Test code argument."""
        from gdb_mcp.server import ExecutePythonArgs

        args = ExecutePythonArgs(code="print('hello')")
        assert args.code == "print('hello')"
