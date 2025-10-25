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
        assert not "info threads".startswith('-')
        assert not "print x".startswith('-')

        # MI commands start with '-'
        assert "-break-list".startswith('-')
        assert "-exec-run".startswith('-')


class TestGDBSessionWithMock:
    """Test cases that mock the GdbController."""

    @patch('gdb_mcp.gdb_interface.GdbController')
    def test_start_session_already_running(self, mock_controller_class):
        """Test starting a session when one is already running."""
        session = GDBSession()

        # Manually set controller to simulate running session
        session.controller = Mock()

        result = session.start(program="/bin/ls")

        assert result["status"] == "error"
        assert "already running" in result["message"].lower()

    @patch('gdb_mcp.gdb_interface.GdbController')
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
        result = session.start(program="/bin/ls")

        assert result["status"] == "success"
        assert result["program"] == "/bin/ls"
        assert session.is_running is True

    @patch('gdb_mcp.gdb_interface.GdbController')
    def test_start_session_with_custom_gdb_path(self, mock_controller_class):
        """Test session start with custom GDB path."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller
        mock_controller.get_gdb_response.return_value = []

        session = GDBSession()
        result = session.start(
            program="/bin/ls",
            gdb_path="/usr/local/bin/gdb-custom"
        )

        # Verify GdbController was called with correct command
        call_args = mock_controller_class.call_args
        command = call_args[1]["command"]

        assert command[0] == "/usr/local/bin/gdb-custom"
        assert "--interpreter=mi" in command
        assert result["status"] == "success"

    @patch('gdb_mcp.gdb_interface.GdbController')
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

    @patch('gdb_mcp.gdb_interface.GdbController')
    def test_start_session_detects_missing_debug_symbols(self, mock_controller_class):
        """Test that missing debug symbols are detected."""
        mock_controller = MagicMock()
        mock_controller_class.return_value = mock_controller

        # Mock response with "no debugging symbols" warning
        mock_controller.get_gdb_response.return_value = [
            {"type": "console", "payload": "Reading symbols from /bin/ls...\n"},
            {"type": "console", "payload": "(no debugging symbols found)...done.\n"}
        ]

        session = GDBSession()
        result = session.start(program="/bin/ls")

        assert result["status"] == "success"
        assert "warnings" in result
        assert any("not compiled with -g" in w for w in result["warnings"])
