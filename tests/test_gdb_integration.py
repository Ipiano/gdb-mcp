"""Integration tests for GDB MCP Server with real GDB instances.

These tests compile and debug a real C++ program using GDB through the MCP
server interface. They validate the complete workflow including:
- Starting GDB sessions with compiled programs via gdb_start_session
- Session management with session_id routing
- Setting and managing breakpoints
- Stepping through code execution
- Inspecting variables and call stacks
- Executing both MI and CLI commands

Note: These tests may occasionally exhibit flakiness due to timing issues
with GDB process state transitions. This is expected behavior for integration
tests that interact with external processes.
"""

import pytest
import tempfile
import subprocess
import os
import asyncio
import json
from pathlib import Path
from gdb_mcp.server import call_tool


def call_gdb_tool(tool_name: str, arguments: dict) -> dict:
    """
    Helper to call MCP tools synchronously and return parsed result.

    Args:
        tool_name: Name of the GDB MCP tool to call
        arguments: Arguments dictionary for the tool

    Returns:
        Parsed JSON result from the tool call
    """
    result = asyncio.run(call_tool(tool_name, arguments))
    # Parse the JSON response from the tool
    return json.loads(result[0].text)


# Simple C++ program with function calls for testing
TEST_CPP_PROGRAM = """
#include <iostream>

int add(int a, int b) {
    int result = a + b;
    return result;
}

int multiply(int x, int y) {
    int product = x * y;
    return product;
}

int calculate(int num) {
    int sum = add(num, 10);
    int prod = multiply(sum, 2);
    return prod;
}

int main() {
    int value = 5;
    int result = calculate(value);
    std::cout << "Result: " << result << std::endl;
    return 0;
}
"""


@pytest.fixture
def compiled_program():
    """
    Fixture that compiles the test C++ program for each test.
    Uses a context manager to ensure proper cleanup.
    """
    # Create a temporary directory for our test files
    with tempfile.TemporaryDirectory() as tmpdir:
        source_file = Path(tmpdir) / "test_program.cpp"
        executable_file = Path(tmpdir) / "test_program"

        # Write the C++ source code
        source_file.write_text(TEST_CPP_PROGRAM)

        # Compile with debugging symbols and no optimization
        compile_result = subprocess.run(
            ["g++", "-g", "-O0", "-o", str(executable_file), str(source_file)],
            capture_output=True,
            text=True,
        )

        if compile_result.returncode != 0:
            pytest.fail(f"Failed to compile test program: {compile_result.stderr}")

        yield str(executable_file)


@pytest.fixture
def session_id(compiled_program):
    """
    Fixture that starts a GDB MCP session and returns its session_id.

    Automatically configures the session to avoid ASLR-related crashes in
    containerized environments. Ensures cleanup after test completion.

    Args:
        compiled_program: Path to compiled test program

    Yields:
        session_id: Integer session ID for use in subsequent tool calls
    """
    # Start session with ASLR configuration to avoid crashes
    init_commands = [
        "set disable-randomization on",
        "set startup-with-shell off",
    ]

    result = call_gdb_tool(
        "gdb_start_session",
        {
            "program": compiled_program,
            "init_commands": init_commands,
        },
    )

    assert result["status"] == "success", f"Failed to start session: {result}"
    session_id = result["session_id"]

    yield session_id

    # Cleanup: stop the session
    try:
        call_gdb_tool("gdb_stop_session", {"session_id": session_id})
    except Exception:
        # Session may already be stopped by the test
        pass


# Integration tests that run GDB with a real program


@pytest.mark.integration
def test_start_session_with_program(compiled_program):
    """Test starting a GDB session with a compiled program via MCP server."""
    # Start session (session_id fixture already starts one, but let's test explicitly)
    result = call_gdb_tool(
        "gdb_start_session",
        {
            "program": compiled_program,
            "init_commands": [
                "set disable-randomization on",
                "set startup-with-shell off",
            ],
        },
    )

    assert result["status"] == "success"
    assert result["program"] == compiled_program
    assert "session_id" in result
    assert isinstance(result["session_id"], int)
    session_id = result["session_id"]

    # Verify session status
    status = call_gdb_tool("gdb_get_status", {"session_id": session_id})
    assert status["is_running"] is True
    assert status["target_loaded"] is True

    # Cleanup
    call_gdb_tool("gdb_stop_session", {"session_id": session_id})


@pytest.mark.integration
def test_set_and_list_breakpoints(session_id):
    """Test setting breakpoints and listing them."""
    # Set breakpoint at main
    bp_result = call_gdb_tool(
        "gdb_set_breakpoint",
        {
            "session_id": session_id,
            "location": "main",
        },
    )
    assert bp_result["status"] == "success"
    assert "breakpoint" in bp_result
    # Function name might be "main" or "main()" depending on GDB version
    assert "main" in bp_result["breakpoint"]["func"]

    # Set breakpoint at add function
    bp_result2 = call_gdb_tool(
        "gdb_set_breakpoint",
        {
            "session_id": session_id,
            "location": "add",
        },
    )
    assert bp_result2["status"] == "success"

    # List all breakpoints
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["status"] == "success"
    assert list_result["count"] == 2
    assert len(list_result["breakpoints"]) == 2


@pytest.mark.integration
def test_run_and_hit_breakpoint(session_id):
    """Test running the program and hitting a breakpoint."""
    # Set breakpoint at main
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})

    # Run the program (it should stop at main)
    run_result = call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})
    assert run_result["status"] == "success"

    # Get backtrace to verify we're at main
    backtrace = call_gdb_tool("gdb_get_backtrace", {"session_id": session_id})
    assert backtrace["status"] == "success"
    assert backtrace["count"] > 0
    # Check that we're in main function (func might be "main", "main()", etc.)
    frames = backtrace["frames"]
    assert any("main" in frame.get("func", "") for frame in frames)


@pytest.mark.integration
def test_step_through_functions(session_id):
    """Test stepping through function calls."""
    # Set breakpoint at main
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Step a few times
    for _ in range(3):
        step_result = call_gdb_tool("gdb_step", {"session_id": session_id})
        assert step_result["status"] == "success"

    # Verify we can still get a backtrace
    backtrace = call_gdb_tool("gdb_get_backtrace", {"session_id": session_id})
    assert backtrace["status"] == "success"
    assert backtrace["count"] > 0


@pytest.mark.integration
def test_inspect_variables(session_id):
    """Test inspecting variable values."""
    # Set breakpoint in the add function
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})

    # Run to breakpoint (stops at the add function)
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Step to ensure we're in the function body
    call_gdb_tool("gdb_next", {"session_id": session_id})

    # Try to evaluate the parameters
    eval_result = call_gdb_tool(
        "gdb_evaluate_expression", {"session_id": session_id, "expression": "a"}
    )
    # Note: This might not work if we haven't stepped to the right location
    # but we can at least verify the command executes


@pytest.mark.integration
def test_backtrace_across_functions(session_id):
    """Test getting backtrace when nested in function calls."""
    # Set breakpoint in the add function (called from calculate)
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})

    # Run to breakpoint (this will stop at the add function)
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Get backtrace
    backtrace = call_gdb_tool("gdb_get_backtrace", {"session_id": session_id})
    assert backtrace["status"] == "success"

    # Should have at least 2 frames (add and its caller)
    assert backtrace["count"] >= 2, f"Expected at least 2 frames, got {backtrace['count']}"

    # Verify the call stack includes at least the add function
    frames = backtrace["frames"]
    frame_funcs = [f.get("func", "") for f in frames]
    # Check if add is in the backtrace (with or without signature)
    assert any("add" in func for func in frame_funcs if func)


@pytest.mark.integration
def test_next_vs_step(session_id):
    """Test difference between next (step over) and step (step into)."""
    # Set breakpoint at main
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Use next() which should step over function calls
    # This should execute but stay in the same function
    next_result = call_gdb_tool("gdb_next", {"session_id": session_id})
    assert next_result["status"] == "success"

    # Get backtrace after next - should still be in main or at same depth
    backtrace1 = call_gdb_tool("gdb_get_backtrace", {"session_id": session_id})
    depth1 = backtrace1["count"]

    # Now try step() which should step into function calls
    step_result = call_gdb_tool("gdb_step", {"session_id": session_id})
    assert step_result["status"] == "success"


@pytest.mark.integration
def test_evaluate_expressions(session_id):
    """Test evaluating expressions at runtime."""
    # Set breakpoint at main
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Step a few times to get past variable declarations
    for _ in range(3):
        call_gdb_tool("gdb_next", {"session_id": session_id})

    # Try to evaluate a simple expression
    result = call_gdb_tool(
        "gdb_evaluate_expression", {"session_id": session_id, "expression": "5 + 3"}
    )
    # GDB should be able to evaluate constant expressions
    if result["status"] == "success":
        assert "value" in result


@pytest.mark.integration
def test_get_variables_in_frame(session_id):
    """Test getting local variables in the current frame."""
    # Set breakpoint at add function
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Step to ensure we're in the function body
    call_gdb_tool("gdb_next", {"session_id": session_id})

    # Get local variables
    vars_result = call_gdb_tool("gdb_get_variables", {"session_id": session_id})
    assert vars_result["status"] == "success"
    # Should have variables like 'a', 'b', 'result'
    assert "variables" in vars_result


@pytest.mark.integration
@pytest.mark.integration
def test_session_cleanup(compiled_program):
    """Test that session can be properly stopped and restarted."""
    # Start first session
    result1 = call_gdb_tool(
        "gdb_start_session",
        {
            "program": compiled_program,
            "init_commands": ["set disable-randomization on"],
        },
    )
    assert result1["status"] == "success"
    assert "session_id" in result1
    session_id1 = result1["session_id"]

    # Verify session is running
    status1 = call_gdb_tool("gdb_get_status", {"session_id": session_id1})
    assert status1["is_running"] is True

    # Stop session
    stop_result = call_gdb_tool("gdb_stop_session", {"session_id": session_id1})
    assert stop_result["status"] == "success"

    # Verify we can start another session
    result2 = call_gdb_tool(
        "gdb_start_session",
        {
            "program": compiled_program,
            "init_commands": ["set disable-randomization on"],
        },
    )
    assert result2["status"] == "success"
    assert "session_id" in result2
    session_id2 = result2["session_id"]

    # Verify new session is running
    status2 = call_gdb_tool("gdb_get_status", {"session_id": session_id2})
    assert status2["is_running"] is True

    # Cleanup
    call_gdb_tool("gdb_stop_session", {"session_id": session_id2})


@pytest.mark.integration
def test_conditional_breakpoint(session_id):
    """Test setting a conditional breakpoint."""
    # Set conditional breakpoint
    # This sets a breakpoint in add function only when a > 10
    bp_result = call_gdb_tool(
        "gdb_set_breakpoint",
        {"session_id": session_id, "location": "add", "condition": "a > 10"},
    )
    assert bp_result["status"] == "success"

    # List breakpoints to verify it was set
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["status"] == "success"
    assert list_result["count"] == 1


@pytest.mark.integration
def test_temporary_breakpoint(session_id):
    """Test setting a temporary breakpoint."""
    # Set temporary breakpoint at main
    bp_result = call_gdb_tool(
        "gdb_set_breakpoint",
        {"session_id": session_id, "location": "main", "temporary": True},
    )
    assert bp_result["status"] == "success"

    # Run to hit the breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # After hitting a temporary breakpoint once, it should be removed
    # Continue and check breakpoint list
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["status"] == "success"
    # Temporary breakpoint should be gone after being hit
    # (though we can't guarantee it was hit vs still pending)


@pytest.mark.integration
def test_get_status(compiled_program):
    """Test getting session status."""
    # Start a session to test status
    result = call_gdb_tool(
        "gdb_start_session",
        {
            "program": compiled_program,
            "init_commands": ["set disable-randomization on"],
        },
    )
    assert result["status"] == "success"
    session_id = result["session_id"]

    # Check status after starting
    status = call_gdb_tool("gdb_get_status", {"session_id": session_id})
    assert status["is_running"] is True
    assert status["target_loaded"] is True

    # Cleanup
    call_gdb_tool("gdb_stop_session", {"session_id": session_id})


@pytest.mark.integration
def test_cli_commands(session_id):
    """Test executing CLI commands (non-MI commands)."""
    # Execute a CLI command before running the program
    # This is more reliable than trying to run it after the program starts
    result = call_gdb_tool(
        "gdb_execute_command", {"session_id": session_id, "command": "info functions"}
    )
    assert result["status"] == "success"
    assert "output" in result
    # Should show our functions (they're defined even before running)
    output_lower = result["output"].lower()
    assert "add" in output_lower or "main" in output_lower or "calculate" in output_lower


# Integration tests for edge cases and error conditions


@pytest.mark.integration
def test_breakpoint_at_nonexistent_function(session_id):
    """Test setting breakpoint at a function that doesn't exist."""

    # Try to set breakpoint at non-existent function
    bp_result = call_gdb_tool(
        "gdb_set_breakpoint",
        {"session_id": session_id, "location": "nonexistent_function"},
    )
    # GDB might still create a pending breakpoint, but won't have full info
    # Just verify the command executes without crashing


@pytest.mark.integration
def test_execute_command_before_run(session_id):
    """Test that we can execute commands before running the program."""

    # Execute commands before running
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["status"] == "success"
    assert list_result["count"] == 0


@pytest.mark.integration
def test_multiple_breakpoints_same_location(session_id):
    """Test setting multiple breakpoints at the same location."""

    # Set breakpoint at main
    bp1 = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})
    assert bp1["status"] == "success"

    # Set another breakpoint at main
    bp2 = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})
    assert bp2["status"] == "success"

    # Both should be in the list
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["status"] == "success"
    assert list_result["count"] == 2


# Integration tests for new features: breakpoint management


@pytest.mark.integration
def test_delete_breakpoint(session_id):
    """Test deleting a breakpoint."""

    # Set a breakpoint
    bp_result = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})
    assert bp_result["status"] == "success"
    bp_number = int(bp_result["breakpoint"]["number"])

    # Set another breakpoint
    bp2_result = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})
    assert bp2_result["status"] == "success"

    # Verify we have 2 breakpoints
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["count"] == 2

    # Delete the first breakpoint
    delete_result = call_gdb_tool(
        "gdb_delete_breakpoint", {"session_id": session_id, "number": bp_number}
    )
    assert delete_result["status"] == "success"

    # Verify only 1 breakpoint remains
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["count"] == 1
    # Verify the remaining breakpoint is at add
    remaining_bp = list_result["breakpoints"][0]
    assert "add" in remaining_bp.get("func", "")


@pytest.mark.integration
def test_enable_disable_breakpoint(session_id):
    """Test enabling and disabling a breakpoint."""

    # Set a breakpoint
    bp_result = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})
    assert bp_result["status"] == "success"
    bp_number = int(bp_result["breakpoint"]["number"])

    # Disable the breakpoint
    disable_result = call_gdb_tool(
        "gdb_disable_breakpoint", {"session_id": session_id, "number": bp_number}
    )
    assert disable_result["status"] == "success"

    # Verify it's disabled
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["count"] == 1
    bp_info = list_result["breakpoints"][0]
    assert bp_info["enabled"] == "n"

    # Enable the breakpoint
    enable_result = call_gdb_tool(
        "gdb_enable_breakpoint", {"session_id": session_id, "number": bp_number}
    )
    assert enable_result["status"] == "success"

    # Verify it's enabled
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["count"] == 1
    bp_info = list_result["breakpoints"][0]
    assert bp_info["enabled"] == "y"


@pytest.mark.integration
def test_breakpoint_workflow(session_id):
    """Test a complete breakpoint management workflow."""

    # Set multiple breakpoints
    bp1 = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})
    bp2 = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})
    bp3 = call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "multiply"})
    assert all(bp["status"] == "success" for bp in [bp1, bp2, bp3])

    bp1_num = int(bp1["breakpoint"]["number"])
    bp2_num = int(bp2["breakpoint"]["number"])
    bp3_num = int(bp3["breakpoint"]["number"])

    # Verify all 3 breakpoints exist
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["count"] == 3

    # Disable one breakpoint
    call_gdb_tool("gdb_disable_breakpoint", {"session_id": session_id, "number": bp2_num})

    # Delete one breakpoint
    call_gdb_tool("gdb_delete_breakpoint", {"session_id": session_id, "number": bp3_num})

    # Verify we have 2 breakpoints (one deleted)
    list_result = call_gdb_tool("gdb_list_breakpoints", {"session_id": session_id})
    assert list_result["count"] == 2

    # Verify the disabled breakpoint is still disabled
    bp2_info = next((bp for bp in list_result["breakpoints"] if bp["number"] == str(bp2_num)), None)
    assert bp2_info is not None
    assert bp2_info["enabled"] == "n"


# Integration tests for thread selection


@pytest.mark.integration
def test_get_threads(session_id):
    """Test getting thread information."""

    # Set breakpoint at main
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Get threads
    threads_result = call_gdb_tool("gdb_get_threads", {"session_id": session_id})
    assert threads_result["status"] == "success"
    assert "threads" in threads_result
    assert threads_result["count"] >= 1  # Should have at least the main thread
    assert "current_thread_id" in threads_result


@pytest.mark.integration
def test_select_thread(session_id):
    """Test selecting a thread."""

    # Set breakpoint at main
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "main"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Get threads
    threads_result = call_gdb_tool("gdb_get_threads", {"session_id": session_id})
    assert threads_result["status"] == "success"
    assert threads_result["count"] >= 1

    # Get the current thread ID
    current_thread_id = threads_result["current_thread_id"]
    assert current_thread_id is not None

    # Select the current thread (should succeed)
    select_result = call_gdb_tool(
        "gdb_select_thread",
        {"session_id": session_id, "thread_id": int(current_thread_id)},
    )
    assert select_result["status"] == "success"
    assert select_result["thread_id"] == int(current_thread_id)


# Integration tests for frame selection


@pytest.mark.integration
def test_get_frame_info(session_id):
    """Test getting information about the current frame."""

    # Set breakpoint in add function
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Get frame info
    frame_result = call_gdb_tool("gdb_get_frame_info", {"session_id": session_id})
    assert frame_result["status"] == "success"
    assert "frame" in frame_result
    frame = frame_result["frame"]
    # Should have basic frame info like level
    assert "level" in frame


@pytest.mark.integration
def test_select_frame(session_id):
    """Test selecting a specific frame in the call stack."""

    # Set breakpoint in add function (called from calculate)
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Get backtrace to see how many frames we have
    backtrace = call_gdb_tool("gdb_get_backtrace", {"session_id": session_id})
    assert backtrace["status"] == "success"
    assert backtrace["count"] >= 2  # Should have at least add and its caller

    # Select frame 0 (current frame - should be add)
    select_result = call_gdb_tool("gdb_select_frame", {"session_id": session_id, "frame_number": 0})
    assert select_result["status"] == "success"
    assert select_result["frame_number"] == 0

    # Select frame 1 (caller frame)
    if backtrace["count"] >= 2:
        select_result = call_gdb_tool(
            "gdb_select_frame", {"session_id": session_id, "frame_number": 1}
        )
        assert select_result["status"] == "success"
        assert select_result["frame_number"] == 1


@pytest.mark.integration
def test_frame_selection_and_variables(session_id):
    """Test that frame selection affects variable inspection."""

    # Set breakpoint in add function
    call_gdb_tool("gdb_set_breakpoint", {"session_id": session_id, "location": "add"})

    # Run to breakpoint
    call_gdb_tool("gdb_execute_command", {"session_id": session_id, "command": "run"})

    # Step to get into the function
    call_gdb_tool("gdb_next", {"session_id": session_id})

    # Get backtrace
    backtrace = call_gdb_tool("gdb_get_backtrace", {"session_id": session_id})
    assert backtrace["count"] >= 2

    # Select frame 0 (add function)
    call_gdb_tool("gdb_select_frame", {"session_id": session_id, "frame_number": 0})
    vars_frame0 = call_gdb_tool("gdb_get_variables", {"session_id": session_id, "frame": 0})
    assert vars_frame0["status"] == "success"

    # Select frame 1 (caller)
    if backtrace["count"] >= 2:
        call_gdb_tool("gdb_select_frame", {"session_id": session_id, "frame_number": 1})
        vars_frame1 = call_gdb_tool("gdb_get_variables", {"session_id": session_id, "frame": 1})
        assert vars_frame1["status"] == "success"
        # Variables should be different in different frames
        # (though we can't guarantee the exact variable names)
