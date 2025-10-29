"""Unit tests for GDB interface."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from gdb_mcp.gdb_interface import GDBSession


class TestGDBSession:
    """Test cases for GDBSession class."""

    def test_session_initialization(self):
        """Test that GDBSession initializes correctly."""
        session = GDBSession()
        assert session.controller is None
        assert session.is_running is False
        assert session.target_loaded is False

    def test_get_status_no_session(self):
        """Test get_status when no session is running."""
        session = GDBSession()
        status = session.get_status()
        assert status["is_running"] is False
        assert status["target_loaded"] is False
        assert status["has_controller"] is False

    def test_stop_no_session(self):
        """Test stopping when no session exists."""
        session = GDBSession()
        result = session.stop()
        assert result["status"] == "error"
        assert "No active session" in result["message"]

    def test_execute_command_no_session(self):
        """Test execute_command when no session is running."""
        session = GDBSession()
        result = session.execute_command("info threads")
        assert result["status"] == "error"
        assert "No active GDB session" in result["message"]

    def test_response_parsing(self):
        """Test _parse_responses method."""
        session = GDBSession()

        # Mock responses from GDB
        responses = [
            {"type": "console", "payload": "Test output\n"},
            {"type": "result", "payload": {"msg": "done"}},
            {"type": "notify", "payload": {"msg": "thread-created"}},
        ]

        parsed = session._parse_responses(responses)

        assert "Test output\n" in parsed["console"]
        assert parsed["result"] == {"msg": "done"}
        assert {"msg": "thread-created"} in parsed["notify"]

    def test_cli_command_wrapping(self):
        """Test that CLI commands are properly detected."""
        session = GDBSession()

        # CLI commands don't start with '-'
        assert not "info threads".startswith("-")
        assert not "print x".startswith("-")

        # MI commands start with '-'
        assert "-break-list".startswith("-")
        assert "-exec-run".startswith("-")


class TestGDBSessionWithMock:
    """Test cases that mock the GdbController."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_already_running(self, mock_controller_class):
        """Test starting a session when one is already running."""
        session = GDBSession()

        # Manually set controller to simulate running session
        session.controller = Mock()

        result = session.start(program="/bin/ls")

        assert result["status"] == "error"
        assert "already running" in result["message"].lower()

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_basic(self, mock_controller_class):
        """Test basic session start."""
        # Create a mock controller instance
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller

        # Mock GDB responses
        mock_controller.get_gdb_response.return_value = [
            {"type": "console", "payload": "Reading symbols from /bin/ls...\n"}
        ]

        session = GDBSession()

        # Mock execute_command to return success for readiness check (-thread-info)
        with patch.object(session, "execute_command") as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "result": {"result": {"threads": [{"id": "1"}]}},
            }
            result = session.start(program="/bin/ls")

        assert result["status"] == "success"
        assert result["program"] == "/bin/ls"
        assert session.is_running is True

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_with_custom_gdb_path(self, mock_controller_class):
        """Test session start with custom GDB path."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller
        mock_controller.get_gdb_response.return_value = []

        session = GDBSession()

        # Mock execute_command to return success for readiness check (-thread-info)
        with patch.object(session, "execute_command") as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "result": {"result": {"threads": [{"id": "1"}]}},
            }
            result = session.start(program="/bin/ls", gdb_path="/usr/local/bin/gdb-custom")

        # Verify GdbController was called with correct command
        call_args = mock_controller_class.call_args
        command = call_args[1]["command"]

        assert command[0] == "/usr/local/bin/gdb-custom"
        assert "--interpreter=mi" in command
        assert result["status"] == "success"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_with_env_variables(self, mock_controller_class):
        """Test session start with environment variables."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller
        mock_controller.get_gdb_response.return_value = []

        session = GDBSession()

        # Track calls to execute_command by patching it
        env_commands = []

        def mock_execute(cmd, **kwargs):
            if "set environment" in cmd:
                env_commands.append(cmd)
            return {"status": "success", "command": cmd, "output": ""}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.start(
                program="/bin/ls", env={"DEBUG_MODE": "1", "LOG_LEVEL": "verbose"}
            )

        # Verify environment commands were executed
        assert len(env_commands) == 2
        assert any("DEBUG_MODE" in cmd for cmd in env_commands)
        assert any("LOG_LEVEL" in cmd for cmd in env_commands)

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_detects_missing_debug_symbols(self, mock_controller_class):
        """Test that missing debug symbols are detected."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller

        # Mock response with "no debugging symbols" warning
        mock_controller.get_gdb_response.return_value = [
            {"type": "console", "payload": "Reading symbols from /bin/ls...\n"},
            {"type": "console", "payload": "(no debugging symbols found)...done.\n"},
        ]

        session = GDBSession()

        # Mock execute_command to return success for readiness check (-thread-info)
        with patch.object(session, "execute_command") as mock_execute:
            mock_execute.return_value = {
                "status": "success",
                "result": {"result": {"threads": [{"id": "1"}]}},
            }
            result = session.start(program="/bin/ls")

        assert result["status"] == "success"
        assert "warnings" in result
        assert any("not compiled with -g" in w for w in result["warnings"])

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_with_init_timeout(self, mock_controller_class):
        """Test that init_timeout_sec is passed to execute_command for init commands."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller
        mock_controller.get_gdb_response.return_value = []

        session = GDBSession()

        # Track calls to execute_command
        timeout_values = []

        def mock_execute(cmd, timeout_sec=5, **kwargs):
            timeout_values.append((cmd, timeout_sec))
            # Return success for readiness check to exit early
            return {
                "status": "success",
                "command": cmd,
                "output": "",
                "result": {"result": {"version": "9.0"}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.start(
                program="/bin/ls",
                init_commands=["core-file /path/to/core"],
                init_timeout_sec=60,
            )

        # Verify that the init command was called with the custom timeout
        # First call should be the init command with timeout 60
        assert len(timeout_values) >= 1
        assert timeout_values[0][0] == "core-file /path/to/core"
        assert timeout_values[0][1] == 60
        # There may be additional calls for readiness polling with timeout 2
        assert result["status"] == "success"


class TestThreadOperations:
    """Test cases for thread inspection methods."""

    def test_get_threads_no_session(self):
        """Test get_threads when no session is running."""
        session = GDBSession()
        # Manually set controller to None to simulate no session
        session.controller = None

        result = session.get_threads()
        assert result["status"] == "error"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_threads_success(self, mock_controller_class):
        """Test successful thread retrieval."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        # Mock execute_command to return thread info
        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "threads": [
                            {"id": "1", "name": "main"},
                            {"id": "2", "name": "worker-1"},
                        ],
                        "current-thread-id": "1",
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_threads()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert result["current_thread_id"] == "1"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_backtrace_default(self, mock_controller_class):
        """Test backtrace with default parameters."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {"result": {"stack": [{"level": "0", "func": "main", "file": "test.c"}]}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_backtrace()

        assert result["status"] == "success"
        assert result["count"] == 1
        assert result["thread_id"] is None

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_backtrace_specific_thread(self, mock_controller_class):
        """Test backtrace for a specific thread."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        commands_executed = []

        def mock_execute(cmd, **kwargs):
            commands_executed.append(cmd)
            if "thread-select" in cmd:
                return {"status": "success"}
            return {
                "status": "success",
                "result": {"result": {"stack": []}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_backtrace(thread_id=3)

        assert result["status"] == "success"
        assert any("thread-select 3" in cmd for cmd in commands_executed)


class TestBreakpointOperations:
    """Test cases for breakpoint management."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_set_breakpoint_simple(self, mock_controller_class):
        """Test setting a simple breakpoint."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "bkpt": {
                            "number": "1",
                            "type": "breakpoint",
                            "addr": "0x12345",
                            "func": "main",
                        }
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.set_breakpoint("main")

        assert result["status"] == "success"
        assert "breakpoint" in result
        assert result["breakpoint"]["func"] == "main"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_set_breakpoint_with_condition(self, mock_controller_class):
        """Test setting a conditional breakpoint."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        commands_executed = []

        def mock_execute(cmd, **kwargs):
            commands_executed.append(cmd)
            return {
                "status": "success",
                "result": {"result": {"bkpt": {"number": "1"}}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.set_breakpoint("foo.c:42", condition="x > 10", temporary=True)

        assert result["status"] == "success"
        # Verify the command includes condition and temporary flags
        assert any("-break-insert" in cmd for cmd in commands_executed)

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_list_breakpoints(self, mock_controller_class):
        """Test listing breakpoints."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "BreakpointTable": {
                            "body": [
                                {"number": "1", "type": "breakpoint"},
                                {"number": "2", "type": "breakpoint"},
                            ]
                        }
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.list_breakpoints()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["breakpoints"]) == 2


class TestExecutionControl:
    """Test cases for execution control methods."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_continue_execution(self, mock_controller_class):
        """Test continue execution."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "result": {"result": None}}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.continue_execution()

        assert result["status"] == "success"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_step(self, mock_controller_class):
        """Test step into."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "result": {"result": None}}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.step()

        assert result["status"] == "success"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_next(self, mock_controller_class):
        """Test step over."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "result": {"result": None}}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.next()

        assert result["status"] == "success"

    def test_interrupt_no_controller(self):
        """Test interrupt when no session exists."""
        session = GDBSession()
        result = session.interrupt()

        assert result["status"] == "error"
        assert "No active GDB session" in result["message"]

    @patch("gdb_mcp.gdb_interface.GdbController")
    @patch("gdb_mcp.gdb_interface.os.kill")
    @patch("time.sleep")  # time is imported locally in the method
    def test_interrupt_success(self, mock_sleep, mock_kill, mock_controller_class):
        """Test successful interrupt."""
        mock_controller = MagicMock()
        mock_controller.gdb_process.pid = 12345
        mock_controller.get_gdb_response.return_value = [
            {"type": "notify", "payload": {"msg": "stopped"}}
        ]

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.interrupt()

        assert result["status"] == "success"
        mock_kill.assert_called_once()


class TestDataInspection:
    """Test cases for data inspection methods."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_evaluate_expression(self, mock_controller_class):
        """Test expression evaluation."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {"result": {"value": "42"}},
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.evaluate_expression("x + y")

        assert result["status"] == "success"
        assert result["expression"] == "x + y"
        assert result["value"] == "42"

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_variables(self, mock_controller_class):
        """Test getting local variables."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            if "stack-select-frame" in cmd or "thread-select" in cmd:
                return {"status": "success"}
            return {
                "status": "success",
                "result": {
                    "result": {
                        "variables": [
                            {"name": "x", "value": "10"},
                            {"name": "y", "value": "20"},
                        ]
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_variables(thread_id=2, frame=1)

        assert result["status"] == "success"
        assert result["thread_id"] == 2
        assert result["frame"] == 1
        assert len(result["variables"]) == 2

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_registers(self, mock_controller_class):
        """Test getting register values."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {
                "status": "success",
                "result": {
                    "result": {
                        "register-values": [
                            {"number": "0", "value": "0x1234"},
                            {"number": "1", "value": "0x5678"},
                        ]
                    }
                },
            }

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_registers()

        assert result["status"] == "success"
        assert len(result["registers"]) == 2


class TestSessionManagement:
    """Test cases for session management operations."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_stop_active_session(self, mock_controller_class):
        """Test stopping an active session."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.stop()

        assert result["status"] == "success"
        assert session.controller is None
        assert session.is_running is False

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_stop_session_with_hanging_exit(self, mock_controller_class):
        """Test that stop handles hanging GDB exit by force-killing."""
        import time

        mock_controller = MagicMock()
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is still running

        # Make exit() hang for longer than timeout
        def hanging_exit():
            time.sleep(10)  # Longer than the 1 second timeout we'll use

        mock_controller.exit.side_effect = hanging_exit
        mock_controller.gdb_process = mock_process

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        # Use a very short timeout for the test
        result = session.stop(timeout_sec=1)

        # Should still succeed (force-killed)
        assert result["status"] == "success"
        assert "force killed" in result["message"].lower()
        # State should be cleaned up
        assert session.controller is None
        assert session.is_running is False
        # Process should have been killed
        mock_process.kill.assert_called_once()

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_stop_session_cleans_up_on_error(self, mock_controller_class):
        """Test that stop always cleans up state even if exit fails."""
        mock_controller = MagicMock()
        mock_controller.exit.side_effect = Exception("Exit failed")
        mock_controller.gdb_process = None  # No process to kill

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.stop()

        # Should still clean up state
        assert result["status"] == "success"
        assert session.controller is None
        assert session.is_running is False
        assert session.target_loaded is False

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_execute_command_cli(self, mock_controller_class):
        """Test executing a CLI command with active session."""
        mock_controller = MagicMock()
        mock_controller.write.return_value = [
            {"type": "console", "payload": "Thread 1 (main)\n"},
            {"type": "result", "payload": None},
        ]

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.execute_command("info threads")

        assert result["status"] == "success"
        assert "Thread 1" in result["output"]

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_execute_command_mi(self, mock_controller_class):
        """Test executing an MI command with active session."""
        mock_controller = MagicMock()
        mock_controller.write.return_value = [
            {"type": "result", "payload": {"threads": []}},
        ]

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.execute_command("-thread-info")

        assert result["status"] == "success"
        assert "result" in result


class TestErrorHandling:
    """Test cases for error handling."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_exception(self, mock_controller_class):
        """Test that start handles exceptions gracefully."""
        mock_controller_class.side_effect = Exception("GDB not found")

        session = GDBSession()
        result = session.start(program="/bin/ls")

        assert result["status"] == "error"
        assert "GDB not found" in result["message"]

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_execute_command_exception(self, mock_controller_class):
        """Test that execute_command handles exceptions."""
        mock_controller = MagicMock()
        mock_controller.write.side_effect = Exception("Timeout")

        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        result = session.execute_command("info threads")

        assert result["status"] == "error"
        assert "Timeout" in result["message"]

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_set_breakpoint_no_result(self, mock_controller_class):
        """Test set_breakpoint when GDB returns no result."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "result": {"result": None}}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.set_breakpoint("main")

        assert result["status"] == "error"
        assert "no result from GDB" in result["message"]


class TestNoneResultHandling:
    """Test cases for handling None results from GDB/MI commands."""

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_backtrace_with_none_result(self, mock_controller_class):
        """Test that get_backtrace handles None result payload gracefully."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            # Simulate GDB returning None for result (can happen in cross-arch debugging)
            return {"status": "success", "command": cmd, "result": None}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_backtrace(thread_id=1, max_frames=25)

        assert result["status"] == "success"
        assert result["frames"] == []
        assert result["count"] == 0

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_threads_with_none_result(self, mock_controller_class):
        """Test that get_threads handles None result payload gracefully."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "command": cmd, "result": None}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_threads()

        assert result["status"] == "success"
        assert result["threads"] == []
        assert result["count"] == 0

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_evaluate_expression_with_none_result(self, mock_controller_class):
        """Test that evaluate_expression handles None result payload gracefully."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "command": cmd, "result": None}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.evaluate_expression("x + y")

        assert result["status"] == "success"
        assert result["expression"] == "x + y"
        assert result["value"] is None

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_variables_with_none_result(self, mock_controller_class):
        """Test that get_variables handles None result payload gracefully."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        call_count = [0]

        def mock_execute(cmd, **kwargs):
            call_count[0] += 1
            # First two calls are thread-select and stack-select-frame
            # Third call is the actual stack-list-variables
            if call_count[0] <= 2:
                return {"status": "success", "command": cmd, "result": {"result": {}}}
            return {"status": "success", "command": cmd, "result": None}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_variables(thread_id=1, frame=0)

        assert result["status"] == "success"
        assert result["variables"] == []

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_get_registers_with_none_result(self, mock_controller_class):
        """Test that get_registers handles None result payload gracefully."""
        mock_controller = MagicMock()
        session = GDBSession()
        session.controller = mock_controller
        session.is_running = True

        def mock_execute(cmd, **kwargs):
            return {"status": "success", "command": cmd, "result": None}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.get_registers()

        assert result["status"] == "success"
        assert result["registers"] == []


class TestGDBCrashDetection:
    """Test cases for detecting GDB crashes during initialization."""

    def test_check_for_gdb_crash_detects_fatal_error(self):
        """Test that _check_for_gdb_crash detects GDB fatal errors."""
        session = GDBSession()

        # Simulate a command result with GDB crash messages
        crash_result = {
            "status": "success",
            "result": {
                "log": [
                    "Some normal log message\n",
                    "A fatal error internal to GDB has been detected, further\ndebugging is not possible.\n",
                    "GDB will now terminate.\n",
                ]
            },
        }

        assert session._check_for_gdb_crash(crash_result) is True

    def test_check_for_gdb_crash_detects_fatal_signal(self):
        """Test that _check_for_gdb_crash detects GDB fatal signals."""
        session = GDBSession()

        crash_result = {
            "status": "success",
            "result": {
                "log": [
                    "Fatal signal: Segmentation fault\n",
                    "Backtrace unavailable\n",
                ]
            },
        }

        assert session._check_for_gdb_crash(crash_result) is True

    def test_check_for_gdb_crash_no_crash(self):
        """Test that _check_for_gdb_crash returns False for normal output."""
        session = GDBSession()

        normal_result = {
            "status": "success",
            "result": {
                "log": [
                    "Reading symbols from /bin/ls...\n",
                    "Done.\n",
                ]
            },
        }

        assert session._check_for_gdb_crash(normal_result) is False

    def test_check_for_gdb_crash_error_status(self):
        """Test that _check_for_gdb_crash returns False for error status."""
        session = GDBSession()

        error_result = {
            "status": "error",
            "message": "Command failed",
        }

        assert session._check_for_gdb_crash(error_result) is False

    @patch("gdb_mcp.gdb_interface.GdbController")
    def test_start_session_detects_gdb_crash(self, mock_controller_class):
        """Test that start() detects and reports GDB crashes during init commands."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller
        mock_controller.get_gdb_response.return_value = []

        session = GDBSession()

        # Mock execute_command to simulate a GDB crash on the second init command
        call_count = [0]

        def mock_execute(cmd, **kwargs):
            call_count[0] += 1
            if "core-file" in cmd:
                # Simulate GDB crash
                return {
                    "status": "success",
                    "command": cmd,
                    "result": {
                        "log": [
                            "Fatal signal: Segmentation fault\n",
                            "A fatal error internal to GDB has been detected, further\ndebugging is not possible.\n",
                        ]
                    },
                }
            return {"status": "success", "command": cmd, "result": {"log": []}}

        with patch.object(session, "execute_command", side_effect=mock_execute):
            result = session.start(
                init_commands=["set sysroot /path", "core-file /path/to/core"],
                init_timeout_sec=30,
            )

        # Should detect crash and return error
        assert result["status"] == "error"
        assert "crashed" in result["message"].lower()
        assert "error_type" in result
        assert result["error_type"] == "gdb_crash"
        # State should be cleaned up
        assert session.controller is None
        assert session.is_running is False
        assert session.target_loaded is False
