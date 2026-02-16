"""Unit tests for SessionManager class."""

import threading
from unittest.mock import Mock, patch
import pytest

from gdb_mcp.server import SessionManager
from gdb_mcp.gdb_interface import GDBSession


class TestSessionManager:
    """Test cases for SessionManager class."""

    def test_create_session_returns_sequential_ids(self):
        """Test that create_session returns sequential integer IDs starting at 1."""
        manager = SessionManager()

        session_id_1 = manager.create_session()
        session_id_2 = manager.create_session()
        session_id_3 = manager.create_session()

        assert session_id_1 == 1
        assert session_id_2 == 2
        assert session_id_3 == 3

    def test_get_session_returns_correct_session(self):
        """Test that get_session returns the correct GDBSession for a given ID."""
        manager = SessionManager()

        session_id = manager.create_session()
        session = manager.get_session(session_id)

        assert session is not None
        assert isinstance(session, GDBSession)

        # Verify it's the same session on repeated calls
        same_session = manager.get_session(session_id)
        assert same_session is session

    def test_get_session_returns_none_for_invalid_id(self):
        """Test that get_session returns None for non-existent session IDs."""
        manager = SessionManager()

        # Test various invalid IDs
        assert manager.get_session(999) is None
        assert manager.get_session(0) is None
        assert manager.get_session(-1) is None

        # Create a session and test ID that doesn't exist
        session_id = manager.create_session()
        assert manager.get_session(session_id + 1) is None

    def test_remove_session_deletes_session(self):
        """Test that remove_session deletes a session and get_session returns None."""
        manager = SessionManager()

        session_id = manager.create_session()
        session = manager.get_session(session_id)
        assert session is not None

        # Remove the session
        result = manager.remove_session(session_id)
        assert result is True

        # Verify it's gone
        assert manager.get_session(session_id) is None

    def test_remove_session_returns_false_for_nonexistent(self):
        """Test that remove_session returns False for already-removed or non-existent IDs."""
        manager = SessionManager()

        # Try removing non-existent ID
        assert manager.remove_session(999) is False

        # Create and remove a session, then try removing again
        session_id = manager.create_session()
        assert manager.remove_session(session_id) is True
        assert manager.remove_session(session_id) is False  # Double remove

    def test_concurrent_create_session_thread_safe(self):
        """Test that concurrent create_session calls produce unique IDs (thread-safe)."""
        manager = SessionManager()
        session_ids = []
        session_ids_lock = threading.Lock()

        def create_sessions():
            """Worker function to create a session and record its ID."""
            session_id = manager.create_session()
            with session_ids_lock:
                session_ids.append(session_id)

        # Launch 10 threads concurrently
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_sessions)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify we got 10 unique IDs
        assert len(session_ids) == 10
        assert len(set(session_ids)) == 10  # All unique

        # Verify IDs are sequential (1 through 10)
        assert sorted(session_ids) == list(range(1, 11))
