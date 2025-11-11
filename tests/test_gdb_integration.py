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
