"""GDB/MI interface for programmatic control of GDB sessions."""

import os
import signal
import subprocess
import threading
import time
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
        env: Optional[Dict[str, str]] = None,
        gdb_path: str = "gdb",
        time_to_check_for_additional_output_sec: float = 0.2,
        init_timeout_sec: int = 30,
    ) -> Dict[str, Any]:
        """
        Start a new GDB session.

        Args:
            program: Path to the executable to debug
            args: Command-line arguments for the program
            init_commands: List of GDB commands to run on startup (e.g., loading core dumps)
            env: Environment variables to set for the debugged program
            gdb_path: Path to GDB executable
            time_to_check_for_additional_output_sec: Time to wait for GDB output
            init_timeout_sec: Timeout for initialization in seconds (default 30s, covers init commands and readiness polling)

        Returns:
            Dict with status and any output messages

        Example init_commands:
            ["file /path/to/executable",
             "core-file /path/to/core",
             "set sysroot /path/to/sysroot",
             "set solib-search-path /path/to/libs"]

        Example env:
            {"LD_LIBRARY_PATH": "/custom/libs", "DEBUG_MODE": "1"}
        """
        if self.controller:
            return {"status": "error", "message": "Session already running. Stop it first."}

        try:
            session_start_time = time.time()
            print(f"\n[GDB SESSION] Starting GDB session...", flush=True)
            # Start GDB in MI mode
            # Build command list: [gdb_path, --quiet, --interpreter=mi, ...]
            # --quiet suppresses the copyright/license banner
            gdb_command = [gdb_path, "--quiet", "--interpreter=mi"]
            if program:
                gdb_command.extend(["--args", program])
                if args:
                    gdb_command.extend(args)

            # pygdbmi 0.11+ uses 'command' parameter instead of 'gdb_path' and 'gdb_args'
            self.controller = GdbController(
                command=gdb_command,
                time_to_check_for_additional_output_sec=time_to_check_for_additional_output_sec,
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

            # Set environment variables for the debugged program if provided
            # These must be set before the program runs
            env_output = []
            if env:
                for var_name, var_value in env.items():
                    # Escape quotes in the value
                    escaped_value = var_value.replace('"', '\\"')
                    env_cmd = f"set environment {var_name} {escaped_value}"
                    result = self.execute_command(env_cmd)
                    env_output.append(result)

            # Run initialization commands if provided
            # Use longer timeout for init commands since operations like loading core dumps can be slow
            init_output = []
            if init_commands:
                print(f"\n[GDB INIT] Running {len(init_commands)} init command(s) with timeout={init_timeout_sec}s", flush=True)
                for i, cmd in enumerate(init_commands, 1):
                    init_start = time.time()
                    print(f"[GDB INIT] Executing init command {i}/{len(init_commands)}: {cmd}", flush=True)
                    result = self.execute_command(cmd, timeout_sec=init_timeout_sec)
                    init_elapsed = time.time() - init_start
                    print(f"[GDB INIT] Init command {i} completed in {init_elapsed:.1f}s, status: {result.get('status')}", flush=True)
                    init_output.append(result)

                    # Check if GDB crashed during this command
                    if self._check_for_gdb_crash(result):
                        print(f"[GDB INIT] ✗ FATAL: GDB crashed while executing: {cmd}", flush=True)
                        logger.error(f"GDB crashed during init command: {cmd}")
                        # Clean up state
                        self.controller = None
                        self.is_running = False
                        self.target_loaded = False
                        return {
                            "status": "error",
                            "message": f"GDB crashed during initialization while executing: {cmd}",
                            "error_type": "gdb_crash",
                            "init_output": init_output,
                        }

                    if "file" in cmd.lower() or "core-file" in cmd.lower():
                        self.target_loaded = True

            if program and not init_commands:
                self.target_loaded = True

            self.is_running = True

            # Build result dict
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

            # Include environment setup output if any
            if env_output:
                result["env_output"] = env_output

            # Include init command output if any
            if init_output:
                result["init_output"] = init_output

            # Wait for GDB to be fully ready after initialization
            # This prevents NoneType errors from background symbol loading
            if self.target_loaded or init_commands:
                print(f"\n[GDB SESSION] Waiting for GDB to be ready after initialization...", flush=True)
                ready_info = self._wait_for_gdb_ready(init_timeout_sec)
                if ready_info.get("ready_warnings"):
                    if "warnings" not in result:
                        result["warnings"] = []
                    result["warnings"].extend(ready_info["ready_warnings"])

            total_elapsed = time.time() - session_start_time
            print(f"[GDB SESSION] ✓ Session started successfully in {total_elapsed:.1f}s", flush=True)

            return result

        except Exception as e:
            logger.error(f"Failed to start GDB session: {e}")
            return {"status": "error", "message": f"Failed to start GDB: {str(e)}"}

    def _wait_for_gdb_ready(self, timeout_sec: int) -> Dict[str, Any]:
        """
        Wait for GDB to be fully ready after initialization commands.

        This polls GDB with simple queries until it responds correctly, indicating
        that background work (like symbol loading) has completed.

        Args:
            timeout_sec: Maximum time to wait for GDB to be ready

        Returns:
            Dict with ready status and any warnings
        """
        start_time = time.time()
        poll_interval = 0.5
        ready_warnings = []
        attempts = 0

        print(f"\n[GDB READINESS] Waiting for GDB to be ready (timeout: {timeout_sec}s)", flush=True)
        logger.info(f"Waiting for GDB to be ready (timeout: {timeout_sec}s)")

        while (time.time() - start_time) < timeout_sec:
            attempts += 1
            elapsed = time.time() - start_time
            remaining = timeout_sec - elapsed
            print(f"[GDB READINESS] === Polling attempt {attempts} at {elapsed:.1f}s (timeout in {remaining:.1f}s) ===", flush=True)

            try:
                # Query the loaded program's thread info to verify the target is fully loaded
                # This checks if the program/core is ready, not just if GDB is responsive
                print(f"[GDB READINESS] Sending -thread-info command to check target readiness...", flush=True)
                cmd_start = time.time()
                response = self.execute_command("-thread-info", timeout_sec=2)
                cmd_elapsed = time.time() - cmd_start
                print(f"[GDB READINESS] Command returned after {cmd_elapsed:.1f}s, status={response.get('status')}", flush=True)

                # Check if we got a valid response about the target
                if response.get("status") == "success":
                    result_payload = response.get("result")
                    if result_payload and result_payload.get("result") is not None:
                        # Check if we actually got thread information back
                        thread_data = result_payload.get("result", {})
                        threads = thread_data.get("threads")
                        if threads is not None:  # Can be empty list for single-threaded
                            elapsed = time.time() - start_time
                            print(f"[GDB READINESS] ✓ Target is ready! Got {len(threads) if isinstance(threads, list) else 'thread'} thread(s) after {elapsed:.1f}s, {attempts} attempts", flush=True)
                            logger.info(f"GDB ready after {elapsed:.1f}s ({attempts} attempts)")
                            return {"ready": True}
                        else:
                            print(f"[GDB READINESS] ✗ Response success but no thread data yet: {result_payload}", flush=True)
                    else:
                        print(f"[GDB READINESS] ✗ Response success but result payload empty: {result_payload}", flush=True)
                else:
                    print(f"[GDB READINESS] ✗ Response status not success: {response.get('status')}, message: {response.get('message', 'N/A')}", flush=True)

            except Exception as e:
                cmd_elapsed = time.time() - cmd_start if 'cmd_start' in locals() else 0
                print(f"[GDB READINESS] ✗ Exception after {cmd_elapsed:.1f}s: {type(e).__name__}: {e}", flush=True)
                logger.debug(f"GDB not ready yet (attempt {attempts}): {e}")

            print(f"[GDB READINESS] Sleeping {poll_interval}s before next attempt...", flush=True)
            time.sleep(poll_interval)

        # Timed out waiting for GDB
        elapsed = time.time() - start_time
        warning_msg = f"GDB may not be fully ready after {elapsed:.1f}s ({attempts} attempts, timeout reached)"
        print(f"[GDB READINESS] ✗ TIMEOUT: {warning_msg}", flush=True)
        logger.warning(warning_msg)
        ready_warnings.append(warning_msg)

        return {"ready": False, "ready_warnings": ready_warnings}

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
            return {"status": "error", "message": "No active GDB session"}

        try:
            # Detect if this is a CLI command (doesn't start with '-')
            # CLI commands need to be wrapped with -interpreter-exec
            is_cli_command = not command.strip().startswith("-")
            actual_command = command

            if is_cli_command:
                # Escape quotes in the command
                escaped_command = command.replace('"', '\\"')
                actual_command = f'-interpreter-exec console "{escaped_command}"'
                logger.debug(f"Wrapping CLI command: {command} -> {actual_command}")

            # Send command and get response
            responses = self.controller.write(actual_command, timeout_sec=timeout_sec)

            # TEMPORARY DEBUG: Print all raw GDB responses
            print(f"\n[GDB DEBUG] Command: {command}")
            print(f"[GDB DEBUG] Raw responses ({len(responses)} items):")
            for i, resp in enumerate(responses):
                print(f"[GDB DEBUG]   [{i}] {resp}")
            print("[GDB DEBUG] ---")

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
                }
            else:
                # For MI commands, return structured result
                return {"status": "success", "command": command, "result": result}

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {"status": "error", "command": command, "message": str(e)}

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

    def _check_for_gdb_crash(self, command_result: Dict[str, Any]) -> bool:
        """
        Check if a command result indicates GDB has crashed.

        Args:
            command_result: The result dict from execute_command

        Returns:
            True if GDB crash detected, False otherwise
        """
        # Check for crash indicators in the result
        if command_result.get("status") != "success":
            return False

        result_data = command_result.get("result")
        if not result_data:
            return False

        # Check log messages for GDB crash indicators
        log_messages = result_data.get("log", [])
        crash_indicators = [
            "A fatal error internal to GDB has been detected",
            "further debugging is not possible",
            "GDB will now terminate",
            "Fatal signal:",
        ]

        for log_msg in log_messages:
            if log_msg and any(indicator in log_msg for indicator in crash_indicators):
                return True

        return False

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
        # Handle case where result payload is None
        result_payload = result.get("result") or {}
        thread_info = result_payload.get("result", {})
        threads = thread_info.get("threads", [])
        current_thread = thread_info.get("current-thread-id")

        return {
            "status": "success",
            "threads": threads,
            "current_thread_id": current_thread,
            "count": len(threads),
        }

    def get_backtrace(
        self, thread_id: Optional[int] = None, max_frames: int = 100
    ) -> Dict[str, Any]:
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

        # Handle case where result payload is None (e.g., cross-architecture debugging)
        result_payload = result.get("result") or {}
        stack_data = result_payload.get("result", {})
        frames = stack_data.get("stack", [])

        return {"status": "success", "thread_id": thread_id, "frames": frames, "count": len(frames)}

    def set_breakpoint(
        self, location: str, condition: Optional[str] = None, temporary: bool = False
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
                "raw_result": result,
            }

        # The breakpoint data should be in the "bkpt" field
        bp_info = mi_result if isinstance(mi_result, dict) else {}
        breakpoint = bp_info.get("bkpt", bp_info)  # Sometimes it's directly in the result

        if not breakpoint:
            logger.warning(f"Empty breakpoint result for {location}: {mi_result}")
            return {
                "status": "error",
                "message": f"Breakpoint set but no info returned for {location}",
                "raw_result": result,
            }

        return {"status": "success", "breakpoint": breakpoint}

    def list_breakpoints(self) -> Dict[str, Any]:
        """
        List all breakpoints with structured data.

        Returns:
            Dict with array of breakpoint objects containing:
            - number: Breakpoint number
            - type: Type (breakpoint, watchpoint, etc.)
            - enabled: Whether enabled (y/n)
            - addr: Memory address
            - func: Function name (if available)
            - file: Source file (if available)
            - fullname: Full path to source file (if available)
            - line: Line number (if available)
            - times: Number of times hit
            - original-location: Original location string
        """
        # Use MI command for structured output
        result = self.execute_command("-break-list")

        if result["status"] == "error":
            return result

        # Extract breakpoint table from MI result
        mi_result = result.get("result", {}).get("result", {})

        # The MI response has a BreakpointTable with body containing array of bkpt objects
        bp_table = mi_result.get("BreakpointTable", {})
        breakpoints = bp_table.get("body", [])

        return {"status": "success", "breakpoints": breakpoints, "count": len(breakpoints)}

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
                "result": result,
            }
        except Exception as e:
            logger.error(f"Failed to interrupt program: {e}")
            return {"status": "error", "message": f"Failed to interrupt: {str(e)}"}

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

        # Handle case where result payload is None
        result_payload = result.get("result") or {}
        value = result_payload.get("result", {}).get("value")

        return {"status": "success", "expression": expression, "value": value}

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

        # Handle case where result payload is None
        result_payload = result.get("result") or {}
        variables = result_payload.get("result", {}).get("variables", [])

        return {"status": "success", "thread_id": thread_id, "frame": frame, "variables": variables}

    def get_registers(self) -> Dict[str, Any]:
        """Get register values for current frame."""
        result = self.execute_command("-data-list-register-values x")

        if result["status"] == "error":
            return result

        # Handle case where result payload is None
        result_payload = result.get("result") or {}
        registers = result_payload.get("result", {}).get("register-values", [])

        return {"status": "success", "registers": registers}

    def stop(self, timeout_sec: int = 5) -> Dict[str, Any]:
        """
        Stop the GDB session with timeout protection.

        If GDB doesn't exit gracefully within the timeout, the process will be
        forcibly terminated. The session state is always cleaned up regardless
        of how GDB exits.

        Args:
            timeout_sec: Timeout in seconds for graceful exit (default: 5)

        Returns:
            Dict with status and message
        """
        if not self.controller:
            return {"status": "error", "message": "No active session"}

        controller = self.controller
        gdb_process = controller.gdb_process if hasattr(controller, "gdb_process") else None
        exit_succeeded = False
        was_killed = False

        try:
            # Try graceful exit with timeout
            def exit_gdb():
                nonlocal exit_succeeded
                try:
                    controller.exit()
                    exit_succeeded = True
                except Exception as e:
                    logger.warning(f"Error during GDB exit: {e}")

            exit_thread = threading.Thread(target=exit_gdb, daemon=True)
            exit_thread.start()
            exit_thread.join(timeout=timeout_sec)

            # If thread is still alive, GDB didn't exit - force kill it
            if exit_thread.is_alive():
                logger.warning(
                    f"GDB did not exit within {timeout_sec}s timeout, force killing process"
                )
                if gdb_process and gdb_process.poll() is None:
                    try:
                        gdb_process.kill()
                        gdb_process.wait(timeout=2)
                        was_killed = True
                    except Exception as e:
                        logger.error(f"Failed to kill GDB process: {e}")

        except Exception as e:
            logger.error(f"Failed to stop GDB session: {e}")
        finally:
            # Always clean up state regardless of how we exited
            self.controller = None
            self.is_running = False
            self.target_loaded = False

        if exit_succeeded:
            return {"status": "success", "message": "GDB session stopped"}
        elif was_killed:
            return {
                "status": "success",
                "message": f"GDB session stopped (force killed after {timeout_sec}s timeout)",
            }
        else:
            return {
                "status": "success",
                "message": "GDB session stopped (cleanup completed, exit status unknown)",
            }

    def load_file(
        self,
        file_path: str,
        file_type: str = "auto",
        timeout_sec: int = 60,
    ) -> Dict[str, Any]:
        """
        Load a file (executable, core dump, or symbol file) and wait for GDB to be ready.

        This is the preferred method for loading files after session start, as it
        includes readiness polling to ensure GDB has finished background processing.

        Args:
            file_path: Path to the file to load
            file_type: Type of file - "executable", "core", "symbols", or "auto" (default)
            timeout_sec: Timeout for loading and readiness check (default: 60s)

        Returns:
            Dict with status and output
        """
        if not self.controller:
            return {"status": "error", "message": "No active GDB session"}

        # Determine the GDB command based on file type
        if file_type == "auto":
            # Try to infer from file path or use 'file' command
            if "core" in file_path.lower():
                file_type = "core"
            else:
                file_type = "executable"

        command_map = {
            "executable": f"file {file_path}",
            "core": f"core-file {file_path}",
            "symbols": f"symbol-file {file_path}",
        }

        if file_type not in command_map:
            return {
                "status": "error",
                "message": f"Invalid file_type: {file_type}. Must be 'executable', 'core', 'symbols', or 'auto'",
            }

        command = command_map[file_type]
        print(f"\n[GDB LOAD FILE] Loading {file_type} file: {file_path}", flush=True)
        print(f"[GDB LOAD FILE] Using command: {command}", flush=True)
        print(f"[GDB LOAD FILE] Timeout: {timeout_sec}s", flush=True)

        # Execute the load command
        load_start = time.time()
        result = self.execute_command(command, timeout_sec=timeout_sec)
        load_elapsed = time.time() - load_start
        print(f"[GDB LOAD FILE] Load command completed in {load_elapsed:.1f}s, status: {result.get('status')}", flush=True)

        if result.get("status") == "error":
            return result

        # Check if GDB crashed during load
        if self._check_for_gdb_crash(result):
            print(f"[GDB LOAD FILE] ✗ FATAL: GDB crashed while loading file", flush=True)
            logger.error(f"GDB crashed while loading {file_type} file: {file_path}")
            # Clean up state
            self.controller = None
            self.is_running = False
            self.target_loaded = False
            return {
                "status": "error",
                "message": f"GDB crashed while loading {file_type} file: {file_path}",
                "error_type": "gdb_crash",
                "load_output": result,
            }

        # Mark target as loaded
        if file_type in ["executable", "core"]:
            self.target_loaded = True

        # Wait for GDB to be ready after loading
        print(f"\n[GDB LOAD FILE] Waiting for GDB to be ready after loading {file_type} file...", flush=True)
        ready_info = self._wait_for_gdb_ready(timeout_sec)

        # Build response
        response = {
            "status": "success",
            "message": f"Loaded {file_type} file: {file_path}",
            "file_path": file_path,
            "file_type": file_type,
            "load_output": result.get("output", result.get("result")),
        }

        if ready_info.get("ready_warnings"):
            response["warnings"] = ready_info["ready_warnings"]

        total_elapsed = time.time() - load_start
        print(f"[GDB LOAD FILE] ✓ File loaded and ready in {total_elapsed:.1f}s", flush=True)

        return response

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the GDB session."""
        return {
            "is_running": self.is_running,
            "target_loaded": self.target_loaded,
            "has_controller": self.controller is not None,
        }
