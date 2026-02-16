"""Unit tests for session routing in call_tool()."""

import asyncio
import json
import pytest
from unittest.mock import Mock, patch


class TestSessionRouting:
    """Test that call_tool() routes to correct GDBSession instances."""

    @patch("gdb_mcp.server.session_manager")
    def test_start_session_returns_session_id(self, mock_manager):
        """Test gdb_start_session creates session and returns session_id."""
        from gdb_mcp.server import call_tool

        # Mock the session manager
        mock_session = Mock()
        mock_session.start.return_value = {"status": "success", "message": "Session started"}
        mock_manager.create_session.return_value = 42
        mock_manager.get_session.return_value = mock_session

        # Call start_session (synchronous call to async function)
        result = asyncio.run(call_tool("gdb_start_session", {}))

        # Verify session was created
        mock_manager.create_session.assert_called_once()

        # Verify response contains session_id
        result_data = json.loads(result[0].text)
        assert result_data["status"] == "success"
        assert result_data["session_id"] == 42

    @patch("gdb_mcp.server.session_manager")
    def test_tool_with_valid_session_id_works(self, mock_manager):
        """Test that tools work with valid session_id."""
        from gdb_mcp.server import call_tool

        # Mock the session manager
        mock_session = Mock()
        mock_session.get_status.return_value = {"status": "success", "running": False}
        mock_manager.get_session.return_value = mock_session

        # Call tool with valid session_id
        result = asyncio.run(call_tool("gdb_get_status", {"session_id": 1}))

        # Verify correct session was retrieved
        mock_manager.get_session.assert_called_once_with(1)
        mock_session.get_status.assert_called_once()

        # Verify result
        result_data = json.loads(result[0].text)
        assert result_data["status"] == "success"

    @patch("gdb_mcp.server.session_manager")
    def test_tool_with_invalid_session_id_returns_error(self, mock_manager):
        """Test that tools return error for invalid session_id."""
        from gdb_mcp.server import call_tool

        # Mock the session manager to return None (invalid session)
        mock_manager.get_session.return_value = None

        # Call tool with invalid session_id
        result = asyncio.run(call_tool("gdb_get_status", {"session_id": 999}))

        # Verify error response
        result_data = json.loads(result[0].text)
        assert result_data["status"] == "error"
        assert "Invalid session_id: 999" in result_data["message"]
        assert "gdb_start_session" in result_data["message"]

    @patch("gdb_mcp.server.session_manager")
    def test_stop_session_removes_from_manager(self, mock_manager):
        """Test that gdb_stop_session removes session from manager."""
        from gdb_mcp.server import call_tool

        # Mock the session manager
        mock_session = Mock()
        mock_session.stop.return_value = {"status": "success", "message": "Session stopped"}
        mock_manager.get_session.return_value = mock_session
        mock_manager.remove_session.return_value = True

        # Call stop_session
        result = asyncio.run(call_tool("gdb_stop_session", {"session_id": 1}))

        # Verify session was stopped and removed
        mock_manager.get_session.assert_called_once_with(1)
        mock_session.stop.assert_called_once()
        mock_manager.remove_session.assert_called_once_with(1)

        # Verify result
        result_data = json.loads(result[0].text)
        assert result_data["status"] == "success"

    @patch("gdb_mcp.server.session_manager")
    def test_execute_command_routes_to_correct_session(self, mock_manager):
        """Test that gdb_execute_command routes to correct session."""
        from gdb_mcp.server import call_tool

        # Mock the session manager with session 5
        mock_session = Mock()
        mock_session.execute_command.return_value = {"status": "success", "output": "Thread info"}
        mock_manager.get_session.return_value = mock_session

        # Call with session_id=5
        result = asyncio.run(
            call_tool("gdb_execute_command", {"session_id": 5, "command": "info threads"})
        )

        # Verify correct session was used
        mock_manager.get_session.assert_called_once_with(5)
        mock_session.execute_command.assert_called_once_with(command="info threads")

    @patch("gdb_mcp.server.session_manager")
    def test_set_breakpoint_routes_to_correct_session(self, mock_manager):
        """Test that gdb_set_breakpoint routes to correct session."""
        from gdb_mcp.server import call_tool

        # Mock the session manager
        mock_session = Mock()
        mock_session.set_breakpoint.return_value = {
            "status": "success",
            "breakpoint": {"number": 1, "location": "main"},
        }
        mock_manager.get_session.return_value = mock_session

        # Call with session_id=3
        result = asyncio.run(call_tool("gdb_set_breakpoint", {"session_id": 3, "location": "main"}))

        # Verify correct session was used
        mock_manager.get_session.assert_called_once_with(3)
        mock_session.set_breakpoint.assert_called_once()

    @patch("gdb_mcp.server.session_manager")
    def test_multiple_tools_use_different_sessions(self, mock_manager):
        """Test that different session_ids route to different sessions."""
        from gdb_mcp.server import call_tool

        # Mock two different sessions
        mock_session_1 = Mock()
        mock_session_1.get_status.return_value = {"status": "success", "session": 1}

        mock_session_2 = Mock()
        mock_session_2.get_status.return_value = {"status": "success", "session": 2}

        # Mock get_session to return different sessions based on ID
        def get_session_side_effect(session_id):
            if session_id == 1:
                return mock_session_1
            elif session_id == 2:
                return mock_session_2
            return None

        mock_manager.get_session.side_effect = get_session_side_effect

        # Call with session 1
        result1 = asyncio.run(call_tool("gdb_get_status", {"session_id": 1}))

        # Call with session 2
        result2 = asyncio.run(call_tool("gdb_get_status", {"session_id": 2}))

        # Verify correct sessions were called
        assert mock_manager.get_session.call_count == 2
        mock_session_1.get_status.assert_called_once()
        mock_session_2.get_status.assert_called_once()

        # Verify results are different
        result1_data = json.loads(result1[0].text)
        result2_data = json.loads(result2[0].text)
        assert result1_data["session"] == 1
        assert result2_data["session"] == 2
