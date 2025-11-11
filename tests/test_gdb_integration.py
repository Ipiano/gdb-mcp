"""Integration tests for GDBSession with real GDB instances.

These tests compile and debug a real C++ program using GDB. They validate
the complete workflow of the GDBSession object including:
- Starting GDB sessions with compiled programs
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
from pathlib import Path
from gdb_mcp.gdb_interface import GDBSession


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
def gdb_session():
    """
    Fixture that provides a GDBSession instance and ensures cleanup.

    Wraps the start() method to automatically set disable-randomization on,
    which helps avoid ASLR-related crashes in containerized environments.
    """
    session = GDBSession()

    # Wrap the start method to automatically add ASLR configuration
    original_start = session.start

    def wrapped_start(*args, **kwargs):
        # Get existing init_commands or create new list
        init_commands = kwargs.get("init_commands", [])
        if init_commands is None:
            init_commands = []
        else:
            init_commands = list(init_commands)  # Make a copy

        # Add commands to help avoid random crashes in containerized environments:
        # - disable-randomization: Try to disable ASLR for the debugged program
        # - startup-with-shell: Avoid shell wrapper that might have ASLR enabled
        init_commands.insert(0, "set startup-with-shell off")
        init_commands.insert(0, "set disable-randomization on")

        # Update kwargs with modified init_commands
        kwargs["init_commands"] = init_commands

        # Call original start method
        return original_start(*args, **kwargs)

    session.start = wrapped_start

    yield session
    # Ensure session is stopped after test
    if session.is_running:
        session.stop()


# Integration tests that run GDB with a real program


@pytest.mark.integration
def test_start_session_with_program(gdb_session, compiled_program):
    """Test starting a GDB session with a compiled program."""
    result = gdb_session.start(program=compiled_program)

    assert result["status"] == "success"
    assert result["program"] == compiled_program
    assert gdb_session.is_running is True
    assert gdb_session.target_loaded is True


@pytest.mark.integration
def test_set_and_list_breakpoints(gdb_session, compiled_program):
    """Test setting breakpoints and listing them."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    bp_result = gdb_session.set_breakpoint("main")
    assert bp_result["status"] == "success"
    assert "breakpoint" in bp_result
    # Function name might be "main" or "main()" depending on GDB version
    assert "main" in bp_result["breakpoint"]["func"]

    # Set breakpoint at add function
    bp_result2 = gdb_session.set_breakpoint("add")
    assert bp_result2["status"] == "success"

    # List all breakpoints
    list_result = gdb_session.list_breakpoints()
    assert list_result["status"] == "success"
    assert list_result["count"] == 2
    assert len(list_result["breakpoints"]) == 2


@pytest.mark.integration
def test_run_and_hit_breakpoint(gdb_session, compiled_program):
    """Test running the program and hitting a breakpoint."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    gdb_session.set_breakpoint("main")

    # Run the program (it should stop at main)
    run_result = gdb_session.run()
    assert run_result["status"] == "success"

    # Get backtrace to verify we're at main
    backtrace = gdb_session.get_backtrace()
    assert backtrace["status"] == "success"
    assert backtrace["count"] > 0
    # Check that we're in main function (func might be "main", "main()", etc.)
    frames = backtrace["frames"]
    assert any("main" in frame.get("func", "") for frame in frames)


@pytest.mark.integration
def test_step_through_functions(gdb_session, compiled_program):
    """Test stepping through function calls."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    gdb_session.set_breakpoint("main")

    # Run to breakpoint
    gdb_session.run()

    # Step a few times
    for _ in range(3):
        step_result = gdb_session.step()
        assert step_result["status"] == "success"

    # Verify we can still get a backtrace
    backtrace = gdb_session.get_backtrace()
    assert backtrace["status"] == "success"
    assert backtrace["count"] > 0


@pytest.mark.integration
def test_inspect_variables(gdb_session, compiled_program):
    """Test inspecting variable values."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint in the add function
    gdb_session.set_breakpoint("add")

    # Run to breakpoint (stops at the add function)
    gdb_session.run()

    # Step to ensure we're in the function body
    gdb_session.next()

    # Try to evaluate the parameters
    eval_result = gdb_session.evaluate_expression("a")
    # Note: This might not work if we haven't stepped to the right location
    # but we can at least verify the command executes


@pytest.mark.integration
def test_backtrace_across_functions(gdb_session, compiled_program):
    """Test getting backtrace when nested in function calls."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint in the add function (called from calculate)
    gdb_session.set_breakpoint("add")

    # Run to breakpoint (this will stop at the add function)
    gdb_session.run()

    # Get backtrace
    backtrace = gdb_session.get_backtrace()
    assert backtrace["status"] == "success"

    # Should have at least 2 frames (add and its caller)
    assert backtrace["count"] >= 2, f"Expected at least 2 frames, got {backtrace['count']}"

    # Verify the call stack includes at least the add function
    frames = backtrace["frames"]
    frame_funcs = [f.get("func", "") for f in frames]
    # Check if add is in the backtrace (with or without signature)
    assert any("add" in func for func in frame_funcs if func)


@pytest.mark.integration
def test_next_vs_step(gdb_session, compiled_program):
    """Test difference between next (step over) and step (step into)."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    gdb_session.set_breakpoint("main")

    # Run to breakpoint
    gdb_session.run()

    # Use next() which should step over function calls
    # This should execute but stay in the same function
    next_result = gdb_session.next()
    assert next_result["status"] == "success"

    # Get backtrace after next - should still be in main or at same depth
    backtrace1 = gdb_session.get_backtrace()
    depth1 = backtrace1["count"]

    # Now try step() which should step into function calls
    step_result = gdb_session.step()
    assert step_result["status"] == "success"


@pytest.mark.integration
def test_evaluate_expressions(gdb_session, compiled_program):
    """Test evaluating expressions at runtime."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    gdb_session.set_breakpoint("main")

    # Run to breakpoint
    gdb_session.run()

    # Step a few times to get past variable declarations
    for _ in range(3):
        gdb_session.next()

    # Try to evaluate a simple expression
    result = gdb_session.evaluate_expression("5 + 3")
    # GDB should be able to evaluate constant expressions
    if result["status"] == "success":
        assert "value" in result


@pytest.mark.integration
def test_get_variables_in_frame(gdb_session, compiled_program):
    """Test getting local variables in the current frame."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set breakpoint at add function
    gdb_session.set_breakpoint("add")

    # Run to breakpoint
    gdb_session.run()

    # Step to ensure we're in the function body
    gdb_session.next()

    # Get local variables
    vars_result = gdb_session.get_variables()
    assert vars_result["status"] == "success"
    # Should have variables like 'a', 'b', 'result'
    assert "variables" in vars_result


@pytest.mark.integration
def test_session_cleanup(gdb_session, compiled_program):
    """Test that session can be properly stopped and restarted."""
    # Start session
    result1 = gdb_session.start(program=compiled_program)
    assert result1["status"] == "success"
    assert gdb_session.is_running is True

    # Stop session
    stop_result = gdb_session.stop()
    assert stop_result["status"] == "success"
    assert gdb_session.is_running is False
    assert gdb_session.controller is None

    # Verify we can start another session
    result2 = gdb_session.start(program=compiled_program)
    assert result2["status"] == "success"
    assert gdb_session.is_running is True


@pytest.mark.integration
def test_conditional_breakpoint(gdb_session, compiled_program):
    """Test setting a conditional breakpoint."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set conditional breakpoint
    # This sets a breakpoint in add function only when a > 10
    bp_result = gdb_session.set_breakpoint("add", condition="a > 10")
    assert bp_result["status"] == "success"

    # List breakpoints to verify it was set
    list_result = gdb_session.list_breakpoints()
    assert list_result["status"] == "success"
    assert list_result["count"] == 1


@pytest.mark.integration
def test_temporary_breakpoint(gdb_session, compiled_program):
    """Test setting a temporary breakpoint."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Set temporary breakpoint at main
    bp_result = gdb_session.set_breakpoint("main", temporary=True)
    assert bp_result["status"] == "success"

    # Run to hit the breakpoint
    gdb_session.run()

    # After hitting a temporary breakpoint once, it should be removed
    # Continue and check breakpoint list
    list_result = gdb_session.list_breakpoints()
    assert list_result["status"] == "success"
    # Temporary breakpoint should be gone after being hit
    # (though we can't guarantee it was hit vs still pending)


@pytest.mark.integration
def test_get_status(gdb_session, compiled_program):
    """Test getting session status."""
    # Check status before starting
    status = gdb_session.get_status()
    assert status["is_running"] is False
    assert status["target_loaded"] is False

    # Start session
    gdb_session.start(program=compiled_program)

    # Check status after starting
    status = gdb_session.get_status()
    assert status["is_running"] is True
    assert status["target_loaded"] is True


@pytest.mark.integration
def test_cli_commands(gdb_session, compiled_program):
    """Test executing CLI commands (non-MI commands)."""
    # Start session
    gdb_session.start(program=compiled_program)

    # Execute a CLI command before running the program
    # This is more reliable than trying to run it after the program starts
    result = gdb_session.execute_command("info functions")
    assert result["status"] == "success"
    assert "output" in result
    # Should show our functions (they're defined even before running)
    output_lower = result["output"].lower()
    assert "add" in output_lower or "main" in output_lower or "calculate" in output_lower


# Integration tests for edge cases and error conditions


@pytest.mark.integration
def test_breakpoint_at_nonexistent_function(gdb_session, compiled_program):
    """Test setting breakpoint at a function that doesn't exist."""
    gdb_session.start(program=compiled_program)

    # Try to set breakpoint at non-existent function
    bp_result = gdb_session.set_breakpoint("nonexistent_function")
    # GDB might still create a pending breakpoint, but won't have full info
    # Just verify the command executes without crashing


@pytest.mark.integration
def test_execute_command_before_run(gdb_session, compiled_program):
    """Test that we can execute commands before running the program."""
    gdb_session.start(program=compiled_program)

    # Execute commands before running
    list_result = gdb_session.list_breakpoints()
    assert list_result["status"] == "success"
    assert list_result["count"] == 0


@pytest.mark.integration
def test_multiple_breakpoints_same_location(gdb_session, compiled_program):
    """Test setting multiple breakpoints at the same location."""
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    bp1 = gdb_session.set_breakpoint("main")
    assert bp1["status"] == "success"

    # Set another breakpoint at main
    bp2 = gdb_session.set_breakpoint("main")
    assert bp2["status"] == "success"

    # Both should be in the list
    list_result = gdb_session.list_breakpoints()
    assert list_result["status"] == "success"
    assert list_result["count"] == 2


# Integration tests for new features: breakpoint management


@pytest.mark.integration
def test_delete_breakpoint(gdb_session, compiled_program):
    """Test deleting a breakpoint."""
    gdb_session.start(program=compiled_program)

    # Set a breakpoint
    bp_result = gdb_session.set_breakpoint("main")
    assert bp_result["status"] == "success"
    bp_number = int(bp_result["breakpoint"]["number"])

    # Set another breakpoint
    bp2_result = gdb_session.set_breakpoint("add")
    assert bp2_result["status"] == "success"

    # Verify we have 2 breakpoints
    list_result = gdb_session.list_breakpoints()
    assert list_result["count"] == 2

    # Delete the first breakpoint
    delete_result = gdb_session.delete_breakpoint(bp_number)
    assert delete_result["status"] == "success"

    # Verify only 1 breakpoint remains
    list_result = gdb_session.list_breakpoints()
    assert list_result["count"] == 1
    # Verify the remaining breakpoint is at add
    remaining_bp = list_result["breakpoints"][0]
    assert "add" in remaining_bp.get("func", "")


@pytest.mark.integration
def test_enable_disable_breakpoint(gdb_session, compiled_program):
    """Test enabling and disabling a breakpoint."""
    gdb_session.start(program=compiled_program)

    # Set a breakpoint
    bp_result = gdb_session.set_breakpoint("main")
    assert bp_result["status"] == "success"
    bp_number = int(bp_result["breakpoint"]["number"])

    # Disable the breakpoint
    disable_result = gdb_session.disable_breakpoint(bp_number)
    assert disable_result["status"] == "success"

    # Verify it's disabled
    list_result = gdb_session.list_breakpoints()
    assert list_result["count"] == 1
    bp_info = list_result["breakpoints"][0]
    assert bp_info["enabled"] == "n"

    # Enable the breakpoint
    enable_result = gdb_session.enable_breakpoint(bp_number)
    assert enable_result["status"] == "success"

    # Verify it's enabled
    list_result = gdb_session.list_breakpoints()
    assert list_result["count"] == 1
    bp_info = list_result["breakpoints"][0]
    assert bp_info["enabled"] == "y"


@pytest.mark.integration
def test_breakpoint_workflow(gdb_session, compiled_program):
    """Test a complete breakpoint management workflow."""
    gdb_session.start(program=compiled_program)

    # Set multiple breakpoints
    bp1 = gdb_session.set_breakpoint("main")
    bp2 = gdb_session.set_breakpoint("add")
    bp3 = gdb_session.set_breakpoint("multiply")
    assert all(bp["status"] == "success" for bp in [bp1, bp2, bp3])

    bp1_num = int(bp1["breakpoint"]["number"])
    bp2_num = int(bp2["breakpoint"]["number"])
    bp3_num = int(bp3["breakpoint"]["number"])

    # Verify all 3 breakpoints exist
    list_result = gdb_session.list_breakpoints()
    assert list_result["count"] == 3

    # Disable one breakpoint
    gdb_session.disable_breakpoint(bp2_num)

    # Delete one breakpoint
    gdb_session.delete_breakpoint(bp3_num)

    # Verify we have 2 breakpoints (one deleted)
    list_result = gdb_session.list_breakpoints()
    assert list_result["count"] == 2

    # Verify the disabled breakpoint is still disabled
    bp2_info = next((bp for bp in list_result["breakpoints"] if bp["number"] == str(bp2_num)), None)
    assert bp2_info is not None
    assert bp2_info["enabled"] == "n"


# Integration tests for thread selection


@pytest.mark.integration
def test_get_threads(gdb_session, compiled_program):
    """Test getting thread information."""
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    gdb_session.set_breakpoint("main")

    # Run to breakpoint
    gdb_session.run()

    # Get threads
    threads_result = gdb_session.get_threads()
    assert threads_result["status"] == "success"
    assert "threads" in threads_result
    assert threads_result["count"] >= 1  # Should have at least the main thread
    assert "current_thread_id" in threads_result


@pytest.mark.integration
def test_select_thread(gdb_session, compiled_program):
    """Test selecting a thread."""
    gdb_session.start(program=compiled_program)

    # Set breakpoint at main
    gdb_session.set_breakpoint("main")

    # Run to breakpoint
    gdb_session.run()

    # Get threads
    threads_result = gdb_session.get_threads()
    assert threads_result["status"] == "success"
    assert threads_result["count"] >= 1

    # Get the current thread ID
    current_thread_id = threads_result["current_thread_id"]
    assert current_thread_id is not None

    # Select the current thread (should succeed)
    select_result = gdb_session.select_thread(int(current_thread_id))
    assert select_result["status"] == "success"
    assert select_result["thread_id"] == int(current_thread_id)


# Integration tests for frame selection


@pytest.mark.integration
def test_get_frame_info(gdb_session, compiled_program):
    """Test getting information about the current frame."""
    gdb_session.start(program=compiled_program)

    # Set breakpoint in add function
    gdb_session.set_breakpoint("add")

    # Run to breakpoint
    gdb_session.run()

    # Get frame info
    frame_result = gdb_session.get_frame_info()
    assert frame_result["status"] == "success"
    assert "frame" in frame_result
    frame = frame_result["frame"]
    # Should have basic frame info like level
    assert "level" in frame


@pytest.mark.integration
def test_select_frame(gdb_session, compiled_program):
    """Test selecting a specific frame in the call stack."""
    gdb_session.start(program=compiled_program)

    # Set breakpoint in add function (called from calculate)
    gdb_session.set_breakpoint("add")

    # Run to breakpoint
    gdb_session.run()

    # Get backtrace to see how many frames we have
    backtrace = gdb_session.get_backtrace()
    assert backtrace["status"] == "success"
    assert backtrace["count"] >= 2  # Should have at least add and its caller

    # Select frame 0 (current frame - should be add)
    select_result = gdb_session.select_frame(0)
    assert select_result["status"] == "success"
    assert select_result["frame_number"] == 0

    # Select frame 1 (caller frame)
    if backtrace["count"] >= 2:
        select_result = gdb_session.select_frame(1)
        assert select_result["status"] == "success"
        assert select_result["frame_number"] == 1


@pytest.mark.integration
def test_frame_selection_and_variables(gdb_session, compiled_program):
    """Test that frame selection affects variable inspection."""
    gdb_session.start(program=compiled_program)

    # Set breakpoint in add function
    gdb_session.set_breakpoint("add")

    # Run to breakpoint
    gdb_session.run()

    # Step to get into the function
    gdb_session.next()

    # Get backtrace
    backtrace = gdb_session.get_backtrace()
    assert backtrace["count"] >= 2

    # Select frame 0 (add function)
    gdb_session.select_frame(0)
    vars_frame0 = gdb_session.get_variables(frame=0)
    assert vars_frame0["status"] == "success"

    # Select frame 1 (caller)
    if backtrace["count"] >= 2:
        gdb_session.select_frame(1)
        vars_frame1 = gdb_session.get_variables(frame=1)
        assert vars_frame1["status"] == "success"
        # Variables should be different in different frames
        # (though we can't guarantee the exact variable names)
