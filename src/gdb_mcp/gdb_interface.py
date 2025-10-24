"""GDB/MI interface for programmatic control of GDB sessions."""

import os
import signal
import subprocess
from typing import Optional, List, Dict, Any
from pygdbmi.gdbcontroller import GdbController
import logging

logger = logging.getLogger(__name__)


class GDBSession:
    """
    Manages a GDB debugging session using the GDB/MI (Machine Interface) protocol.

    This class provides a programmatic interface to GDB, similar to how IDEs like
    VS Code and CLion interact with the debugger.
    """

    def __init__(self):
        self.controller: Optional[GdbController] = None
        self.is_running = False
        self.target_loaded = False

    def start(
        self,
        program: Optional[str] = None,
        args: Optional[List[str]] = None,
        init_commands: Optional[List[str]] = None,
        gdb_path: str = "gdb",
        time_to_check_for_additional_output_sec: float = 0.2
    ) -> Dict[str, Any]:
        """
        Start a new GDB session.

        Args:
            program: Path to the executable to debug
            args: Command-line arguments for the program
            init_commands: List of GDB commands to run on startup (e.g., loading core dumps)
            gdb_path: Path to GDB executable
            time_to_check_for_additional_output_sec: Time to wait for GDB output

        Returns:
            Dict with status and any output messages

        Example init_commands:
            ["file /path/to/executable",
             "core-file /path/to/core",
             "set sysroot /path/to/sysroot",
             "set solib-search-path /path/to/libs"]
        """
        if self.controller:
            return {
                "status": "error",
                "message": "Session already running. Stop it first."
            }

        try:
            # Start GDB in MI mode
            # Build command list: [gdb_path, --interpreter=mi, ...]
            gdb_command = [gdb_path, "--interpreter=mi"]
            if program:
                gdb_command.extend(["--args", program])
                if args:
                    gdb_command.extend(args)

            # pygdbmi 0.11+ uses 'command' parameter instead of 'gdb_path' and 'gdb_args'
            self.controller = GdbController(
                command=gdb_command,
                time_to_check_for_additional_output_sec=time_to_check_for_additional_output_sec
            )

            # Get initial responses from GDB startup
            responses = self.controller.get_gdb_response(timeout_sec=2)

            # Parse initial startup messages
            startup_result = self._parse_responses(responses)
            startup_console = "".join(startup_result.get("console", []))

            # Check for common warnings/issues in startup
            warnings = []
            if "no debugging symbols found" in startup_console.lower():
                warnings.append("No debugging symbols found - program was not compiled with -g")
            if "not in executable format" in startup_console.lower():
                warnings.append("File is not an executable")
            if "no such file" in startup_console.lower():
                warnings.append("Program file not found")

            # Run initialization commands if provided
            init_output = []
            if init_commands:
                for cmd in init_commands:
                    result = self.execute_command(cmd)
                    init_output.append(result)
                    if "file" in cmd.lower() or "core-file" in cmd.lower():
                        self.target_loaded = True

            if program and not init_commands:
                self.target_loaded = True

            self.is_running = True

            result = {
                "status": "success",
                "message": f"GDB session started",
                "program": program,
            }

            # Include startup messages if there were any
            if startup_console.strip():
                result["startup_output"] = startup_console.strip()

            # Include warnings if any detected
            if warnings:
                result["warnings"] = warnings

            # Include init command output if any
            if init_output:
                result["init_output"] = init_output

            return result

        except Exception as e:
            logger.error(f"Failed to start GDB session: {e}")
            return {
                "status": "error",
                "message": f"Failed to start GDB: {str(e)}"
            }

    def execute_command(self, command: str, timeout_sec: int = 5) -> Dict[str, Any]:
        """
        Execute a GDB command and return the parsed response.

        Automatically handles both MI commands (starting with '-') and CLI commands.
        CLI commands are wrapped with -interpreter-exec for proper output capture.

        Args:
            command: GDB command to execute (MI or CLI command)
            timeout_sec: Timeout for command execution

        Returns:
            Dict containing the command result and output
        """
        if not self.controller:
            return {
                "status": "error",
                "message": "No active GDB session"
            }

        try:
            # Detect if this is a CLI command (doesn't start with '-')
            # CLI commands need to be wrapped with -interpreter-exec
            is_cli_command = not command.strip().startswith('-')
            actual_command = command

            if is_cli_command:
                # Escape quotes in the command
                escaped_command = command.replace('"', '\\"')
                actual_command = f'-interpreter-exec console "{escaped_command}"'
                logger.debug(f"Wrapping CLI command: {command} -> {actual_command}")

            # Send command and get response
            responses = self.controller.write(actual_command, timeout_sec=timeout_sec)

            # Parse responses
            result = self._parse_responses(responses)

            # For CLI commands, format the output more clearly
            if is_cli_command:
                # Combine all console output
                console_output = "".join(result.get("console", []))

                return {
                    "status": "success",
                    "command": command,
                    "output": console_output.strip() if console_output else "(no output)",
                    "raw_result": result  # Keep raw result for debugging
                }
            else:
                # For MI commands, return structured result
                return {
                    "status": "success",
                    "command": command,
                    "result": result
                }

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {
                "status": "error",
                "command": command,
                "message": str(e)
            }

    def _parse_responses(self, responses: List[Dict]) -> Dict[str, Any]:
        """Parse GDB/MI responses into a structured format."""
        parsed = {
            "console": [],
            "log": [],
            "output": [],
            "result": None,
            "notify": [],
        }

        for response in responses:
            msg_type = response.get("type")

            if msg_type == "console":
                parsed["console"].append(response.get("payload"))
            elif msg_type == "log":
                parsed["log"].append(response.get("payload"))
            elif msg_type == "output":
                parsed["output"].append(response.get("payload"))
            elif msg_type == "result":
                parsed["result"] = response.get("payload")
            elif msg_type == "notify":
                parsed["notify"].append(response.get("payload"))

        return parsed

    def get_threads(self) -> Dict[str, Any]:
        """
        Get information about all threads in the debugged process.

        Returns:
            Dict with thread information
        """
        result = self.execute_command("-thread-info")

        if result["status"] == "error":
            return result

        # Extract thread data from result
        thread_info = result["result"].get("result", {})
        threads = thread_info.get("threads", [])
        current_thread = thread_info.get("current-thread-id")

        return {
            "status": "success",
            "threads": threads,
            "current_thread_id": current_thread,
            "count": len(threads)
        }

    def get_backtrace(self, thread_id: Optional[int] = None, max_frames: int = 100) -> Dict[str, Any]:
        """
        Get the stack backtrace for a specific thread or the current thread.

        Args:
            thread_id: Thread ID to get backtrace for (None for current thread)
            max_frames: Maximum number of frames to retrieve

        Returns:
            Dict with backtrace information
        """
        # Switch to thread if specified
        if thread_id is not None:
            switch_result = self.execute_command(f"-thread-select {thread_id}")
            if switch_result["status"] == "error":
                return switch_result

        # Get stack trace
        result = self.execute_command(f"-stack-list-frames 0 {max_frames}")

        if result["status"] == "error":
            return result

        stack_data = result["result"].get("result", {})
        frames = stack_data.get("stack", [])

        return {
            "status": "success",
            "thread_id": thread_id,
            "frames": frames,
            "count": len(frames)
        }

    def set_breakpoint(
        self,
        location: str,
        condition: Optional[str] = None,
        temporary: bool = False
    ) -> Dict[str, Any]:
        """
        Set a breakpoint at the specified location.

        Args:
            location: Location (function name, file:line, *address)
            condition: Optional condition expression
            temporary: Whether this is a temporary breakpoint

        Returns:
            Dict with breakpoint information
        """
        cmd_parts = ["-break-insert"]

        if temporary:
            cmd_parts.append("-t")

        if condition:
            cmd_parts.extend(["-c", f'"{condition}"'])

        cmd_parts.append(location)

        result = self.execute_command(" ".join(cmd_parts))

        if result["status"] == "error":
            return result

        # The MI result payload is in result["result"]["result"]
        # This contains the actual GDB/MI command result
        mi_result = result.get("result", {}).get("result")

        # Debug logging
        logger.debug(f"Breakpoint MI result: {mi_result}")

        if mi_result is None:
            logger.warning(f"No MI result for breakpoint at {location}")
            return {
                "status": "error",
                "message": f"Failed to set breakpoint at {location}: no result from GDB",
                "raw_result": result
            }

        # The breakpoint data should be in the "bkpt" field
        bp_info = mi_result if isinstance(mi_result, dict) else {}
        breakpoint = bp_info.get("bkpt", bp_info)  # Sometimes it's directly in the result

        if not breakpoint:
            logger.warning(f"Empty breakpoint result for {location}: {mi_result}")
            return {
                "status": "error",
                "message": f"Breakpoint set but no info returned for {location}",
                "raw_result": result
            }

        return {
            "status": "success",
            "breakpoint": breakpoint
        }

    def list_breakpoints(self) -> Dict[str, Any]:
        """
        List all breakpoints.

        Returns:
            Dict with list of breakpoints
        """
        # Use CLI command for more readable output
        result = self.execute_command("info breakpoints")

        if result["status"] == "error":
            return result

        return {
            "status": "success",
            "output": result.get("output", ""),
            "raw_result": result
        }

    def continue_execution(self) -> Dict[str, Any]:
        """Continue execution of the program."""
        return self.execute_command("-exec-continue")

    def step(self) -> Dict[str, Any]:
        """Step into (single instruction)."""
        return self.execute_command("-exec-step")

    def next(self) -> Dict[str, Any]:
        """Step over (next line)."""
        return self.execute_command("-exec-next")

    def interrupt(self) -> Dict[str, Any]:
        """
        Interrupt (pause) a running program.

        This sends SIGINT to the GDB process, which pauses the debugged program.
        Use this when the program is running and you want to pause it to inspect
        state, set breakpoints, or perform other debugging operations.

        Returns:
            Dict with status and message
        """
        if not self.controller:
            return {"status": "error", "message": "No active GDB session"}

        if not self.controller.gdb_process:
            return {"status": "error", "message": "No GDB process running"}

        try:
            # Send SIGINT to pause the running program
            os.kill(self.controller.gdb_process.pid, signal.SIGINT)

            # Give GDB a moment to process the interrupt
            import time
            time.sleep(0.1)

            # Get the response
            responses = self.controller.get_gdb_response(timeout_sec=2)
            result = self._parse_responses(responses)

            return {
                "status": "success",
                "message": "Program interrupted (paused)",
                "result": result
            }
        except Exception as e:
            logger.error(f"Failed to interrupt program: {e}")
            return {
                "status": "error",
                "message": f"Failed to interrupt: {str(e)}"
            }

    def evaluate_expression(self, expression: str) -> Dict[str, Any]:
        """
        Evaluate an expression in the current context.

        Args:
            expression: C/C++ expression to evaluate

        Returns:
            Dict with evaluation result
        """
        result = self.execute_command(f'-data-evaluate-expression "{expression}"')

        if result["status"] == "error":
            return result

        value = result["result"].get("result", {}).get("value")

        return {
            "status": "success",
            "expression": expression,
            "value": value
        }

    def get_variables(self, thread_id: Optional[int] = None, frame: int = 0) -> Dict[str, Any]:
        """
        Get local variables for a specific frame.

        Args:
            thread_id: Thread ID (None for current)
            frame: Frame number (0 is current frame)

        Returns:
            Dict with variable information
        """
        # Switch thread if needed
        if thread_id is not None:
            self.execute_command(f"-thread-select {thread_id}")

        # Select frame
        self.execute_command(f"-stack-select-frame {frame}")

        # Get variables
        result = self.execute_command("-stack-list-variables --simple-values")

        if result["status"] == "error":
            return result

        variables = result["result"].get("result", {}).get("variables", [])

        return {
            "status": "success",
            "thread_id": thread_id,
            "frame": frame,
            "variables": variables
        }

    def get_registers(self) -> Dict[str, Any]:
        """Get register values for current frame."""
        result = self.execute_command("-data-list-register-values x")

        if result["status"] == "error":
            return result

        registers = result["result"].get("result", {}).get("register-values", [])

        return {
            "status": "success",
            "registers": registers
        }

    def stop(self) -> Dict[str, Any]:
        """Stop the GDB session."""
        if not self.controller:
            return {"status": "error", "message": "No active session"}

        try:
            self.controller.exit()
            self.controller = None
            self.is_running = False
            self.target_loaded = False

            return {"status": "success", "message": "GDB session stopped"}

        except Exception as e:
            logger.error(f"Failed to stop GDB session: {e}")
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the GDB session."""
        return {
            "is_running": self.is_running,
            "target_loaded": self.target_loaded,
            "has_controller": self.controller is not None
        }
