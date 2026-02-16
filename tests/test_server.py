"""Unit tests for MCP server."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
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
        args = ExecuteCommandArgs(session_id=1, command="info threads")
        assert args.session_id == 1
        assert args.command == "info threads"


class TestGetBacktraceArgs:
    """Test cases for GetBacktraceArgs model."""

    def test_defaults(self):
        """Test default values."""
        args = GetBacktraceArgs(session_id=1)
        assert args.session_id == 1
        assert args.thread_id is None
        assert args.max_frames == 100

    def test_with_thread_id(self):
        """Test with specific thread ID."""
        args = GetBacktraceArgs(session_id=2, thread_id=5, max_frames=50)
        assert args.session_id == 2
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
        args = SetBreakpointArgs(session_id=1, location="main")
        assert args.session_id == 1
        assert args.location == "main"
        assert args.condition is None
        assert args.temporary is False

    def test_conditional_breakpoint(self):
        """Test conditional breakpoint."""
        args = SetBreakpointArgs(
            session_id=2, location="foo.c:42", condition="x > 10", temporary=True
        )
        assert args.session_id == 2
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
        args = EvaluateExpressionArgs(session_id=1, expression="x + y")
        assert args.session_id == 1
        assert args.expression == "x + y"


class TestGetVariablesArgs:
    """Test cases for GetVariablesArgs model."""

    def test_defaults(self):
        """Test default values."""
        args = GetVariablesArgs(session_id=1)
        assert args.session_id == 1
        assert args.thread_id is None
        assert args.frame == 0

    def test_with_values(self):
        """Test with specific values."""
        args = GetVariablesArgs(session_id=2, thread_id=3, frame=2)
        assert args.session_id == 2
        assert args.thread_id == 3
        assert args.frame == 2


class TestCallFunctionArgs:
    """Test cases for CallFunctionArgs model."""

    def test_function_call_required(self):
        """Test that function_call is required."""
        from gdb_mcp.server import CallFunctionArgs

        with pytest.raises(ValidationError):
            CallFunctionArgs()

    def test_function_call_arg(self):
        """Test function_call argument."""
        from gdb_mcp.server import CallFunctionArgs

        args = CallFunctionArgs(session_id=1, function_call='printf("hello")')
        assert args.session_id == 1
        assert args.function_call == 'printf("hello")'

    def test_function_call_with_args(self):
        """Test function_call with multiple arguments."""
        from gdb_mcp.server import CallFunctionArgs

        args = CallFunctionArgs(session_id=2, function_call='snprintf(buf, 100, "%d", x)')
        assert args.session_id == 2
        assert args.function_call == 'snprintf(buf, 100, "%d", x)'


class TestSessionIdRequired:
    """Test that session_id is required in all tool argument models."""

    def test_execute_command_requires_session_id(self):
        """Test ExecuteCommandArgs requires session_id."""
        with pytest.raises(ValidationError) as exc_info:
            ExecuteCommandArgs(command="info threads")
        assert "session_id" in str(exc_info.value)

    def test_get_backtrace_requires_session_id(self):
        """Test GetBacktraceArgs requires session_id."""
        with pytest.raises(ValidationError) as exc_info:
            GetBacktraceArgs()
        assert "session_id" in str(exc_info.value)

    def test_set_breakpoint_requires_session_id(self):
        """Test SetBreakpointArgs requires session_id."""
        with pytest.raises(ValidationError) as exc_info:
            SetBreakpointArgs(location="main")
        assert "session_id" in str(exc_info.value)

    def test_evaluate_expression_requires_session_id(self):
        """Test EvaluateExpressionArgs requires session_id."""
        with pytest.raises(ValidationError) as exc_info:
            EvaluateExpressionArgs(expression="x + y")
        assert "session_id" in str(exc_info.value)

    def test_get_variables_requires_session_id(self):
        """Test GetVariablesArgs requires session_id."""
        with pytest.raises(ValidationError) as exc_info:
            GetVariablesArgs()
        assert "session_id" in str(exc_info.value)

    def test_thread_select_requires_session_id(self):
        """Test ThreadSelectArgs requires session_id."""
        from gdb_mcp.server import ThreadSelectArgs

        with pytest.raises(ValidationError) as exc_info:
            ThreadSelectArgs(thread_id=1)
        assert "session_id" in str(exc_info.value)

    def test_frame_select_requires_session_id(self):
        """Test FrameSelectArgs requires session_id."""
        from gdb_mcp.server import FrameSelectArgs

        with pytest.raises(ValidationError) as exc_info:
            FrameSelectArgs(frame_number=0)
        assert "session_id" in str(exc_info.value)

    def test_breakpoint_number_requires_session_id(self):
        """Test BreakpointNumberArgs requires session_id."""
        from gdb_mcp.server import BreakpointNumberArgs

        with pytest.raises(ValidationError) as exc_info:
            BreakpointNumberArgs(number=1)
        assert "session_id" in str(exc_info.value)

    def test_call_function_requires_session_id(self):
        """Test CallFunctionArgs requires session_id."""
        from gdb_mcp.server import CallFunctionArgs

        with pytest.raises(ValidationError) as exc_info:
            CallFunctionArgs(function_call='printf("hello")')
        assert "session_id" in str(exc_info.value)

    def test_session_id_validation_success(self):
        """Test that models accept session_id correctly."""
        # ExecuteCommandArgs
        args1 = ExecuteCommandArgs(session_id=1, command="info threads")
        assert args1.session_id == 1

        # GetBacktraceArgs
        args2 = GetBacktraceArgs(session_id=2)
        assert args2.session_id == 2

        # SetBreakpointArgs
        args3 = SetBreakpointArgs(session_id=3, location="main")
        assert args3.session_id == 3
