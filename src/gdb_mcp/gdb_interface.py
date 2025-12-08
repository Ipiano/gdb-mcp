"""GDB/MI interface for programmatic control of GDB sessions."""

import os
import signal
import subprocess
import time
from typing import Any, Optional
from pygdbmi.gdbcontroller import GdbController
import logging

logger = logging.getLogger(__name__)

# Timeout constants (in seconds)
DEFAULT_TIMEOUT_SEC = 30
FILE_LOAD_TIMEOUT_SEC = 300  # 5 minutes for loading core/executable files
INTERRUPT_RESPONSE_TIMEOUT_SEC = 2
POLL_TIMEOUT_SEC = 0.1
INIT_COMMAND_DELAY_SEC = 0.5

# Other constants
INITIAL_COMMAND_TOKEN = 1000
DEFAULT_MAX_BACKTRACE_FRAMES = 100


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
        self.original_cwd: Optional[str] = None  # Store original working directory
        self._command_token = INITIAL_COMMAND_TOKEN

    def start(
        self,
        program: Optional[str] = None,
        args: Optional[list[str]] = None,
        init_commands: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        gdb_path: Optional[str] = None,
        working_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Start a new GDB session.

        Args:
            program: Path to the executable to debug
            args: Command-line arguments for the program
            init_commands: List of GDB commands to run on startup (e.g., loading core dumps)
            env: Environment variables to set for the debugged program
            gdb_path: Path to GDB executable (default: from GDB_PATH env var or 'gdb')
            working_dir: Working directory to use when starting GDB (changes directory
                        before spawning GDB process, then restores it)

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

        # Determine GDB path: explicit parameter > environment variable > default
        if gdb_path is None:
            gdb_path = os.environ.get("GDB_PATH", "gdb")

        # Save current working directory if we need to change it
        # This will be restored when stop() is called
        if working_dir:
            self.original_cwd = os.getcwd()

        try:
            # Change to working directory if specified
            if working_dir:
                if not os.path.isdir(working_dir):
                    return {
                        "status": "error",
                        "message": f"Working directory does not exist: {working_dir}",
                    }
                os.chdir(working_dir)
                logger.info(f"Changed working directory to: {working_dir}")

            # Start GDB in MI mode
            # Build command list: [gdb_path, --quiet, --interpreter=mi, ...]
            # --quiet suppresses the copyright/license banner
            gdb_command = [gdb_path, "--quiet", "--interpreter=mi"]
            if program:
                gdb_command.extend(["--args", program])
                if args:
                    gdb_command.extend(args)

            # pygdbmi 0.11+ uses 'command' parameter instead of 'gdb_path' and 'gdb_args'
            # Use 1.0s for output checking to robustly handle core files with errors/warnings
            self.controller = GdbController(
                command=gdb_command,
                time_to_check_for_additional_output_sec=1.0,
            )

            # Wait for GDB to be ready (send a no-op command and wait for result)
            # This ensures GDB has completed initialization before we send real commands
            # Timeout is based on inactivity - as long as GDB produces output, we wait
            logger.debug("Waiting for GDB initialization to complete...")
            ready_check = self._send_command_and_wait_for_prompt(
                "-gdb-version", timeout_sec=DEFAULT_TIMEOUT_SEC
            )

            if "error" in ready_check or ready_check.get("timed_out"):
                error_msg = ready_check.get("error", "Timeout waiting for GDB to initialize")
                logger.error(f"GDB failed to initialize: {error_msg}")
                # Controller might already be None if fatal error occurred
                if self.controller:
                    try:
                        self.controller.exit()
                    except Exception:
                        pass  # Best effort cleanup
                    self.controller = None
                error_response: dict[str, Any] = {
                    "status": "error",
                    "message": f"GDB failed to initialize: {error_msg}",
                }
                # Propagate fatal flag if present
                if ready_check.get("fatal"):
                    error_response["fatal"] = True
                return error_response

            logger.info("GDB initialized and ready")

            # Parse the version info for startup messages
            startup_result = self._parse_responses(ready_check.get("command_responses", []))
            startup_console = "".join(startup_result.get("console", []))

            # Check for common warnings/issues in startup
            warnings = []
            if "no debugging symbols found" in startup_console.lower():
                warnings.append("No debugging symbols found - program was not compiled with -g")
            if "not in executable format" in startup_console.lower():
                warnings.append("File is not an executable")
            if "no such file" in startup_console.lower():
                warnings.append("Program file not found")

            # Run initialization commands first (before env vars)
            # This allows init_commands to configure GDB settings that affect program loading
            init_output = []
            if init_commands:
                for cmd in init_commands:
                    try:
                        logger.info(f"Executing init command: {cmd}")

                        # Use longer timeout for core-file and file commands
                        # Loading large core dumps can take several minutes
                        if "core-file" in cmd.lower() or cmd.lower().startswith("file "):
                            timeout = FILE_LOAD_TIMEOUT_SEC
                            logger.info(
                                f"Using extended timeout ({timeout}s) for file loading command"
                            )
                        else:
                            timeout = DEFAULT_TIMEOUT_SEC

                        result = self.execute_command(cmd, timeout_sec=timeout)
                        init_output.append(result)

                        # Give GDB time to stabilize after core-file commands
                        # This helps prevent crashes when GDB encounters warnings/errors
                        if "core-file" in cmd.lower():
                            time.sleep(INIT_COMMAND_DELAY_SEC)
                            logger.debug("Waiting for GDB to stabilize after core-file command")

                        # Check if command failed
                        if result.get("status") == "error":
                            error_msg = result.get("message", "Unknown error")
                            logger.error(f"Init command '{cmd}' failed: {error_msg}")

                            # If GDB has died or had fatal error, fail the entire start operation
                            if (
                                result.get("fatal")
                                or "GDB process" in error_msg
                                or not self._is_gdb_alive()
                            ):
                                logger.error("GDB process died during init commands")
                                error_response = {
                                    "status": "error",
                                    "message": f"GDB crashed during init command '{cmd}': {error_msg}",
                                    "init_output": init_output,
                                }
                                # Propagate fatal flag if present
                                if result.get("fatal"):
                                    error_response["fatal"] = True
                                return error_response

                        # Set target_loaded flag for file-related commands
                        # No need to wait explicitly - execute_command waits for (gdb) prompt
                        if "file" in cmd.lower():
                            logger.debug(
                                f"Setting target_loaded=True after file-related command: {cmd}"
                            )
                            self.target_loaded = True
                    except Exception as e:
                        logger.error(f"Exception during init command '{cmd}': {e}", exc_info=True)
                        init_output.append({"status": "error", "command": cmd, "message": str(e)})

                        # If it's a fatal error or GDB died, fail the start operation
                        if not self._is_gdb_alive():
                            logger.error("GDB process died during init command execution")
                            return {
                                "status": "error",
                                "message": f"GDB crashed during init command '{cmd}': {str(e)}",
                                "init_output": init_output,
                            }

            # Set environment variables for the debugged program if provided
            # These must be set before the program runs
            env_output = []
            if env:
                for var_name, var_value in env.items():
                    # Escape backslashes and quotes in the value
                    escaped_value = var_value.replace("\\", "\\\\").replace('"', '\\"')
                    env_cmd = f"set environment {var_name} {escaped_value}"
                    result = self.execute_command(env_cmd)
                    env_output.append(result)

            # Set target_loaded if a program was specified (via --args or init commands)
            if program:
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

            # Include environment setup output if any
            if env_output:
                result["env_output"] = env_output

            # Include init command output if any
            if init_output:
                result["init_output"] = init_output

            return result

        except Exception as e:
            logger.error(f"Failed to start GDB session: {e}")
            # Clean up controller if it was created
            if self.controller:
                try:
                    self.controller.exit()
                except Exception:
                    pass
                self.controller = None
            # If session failed to start, restore working directory immediately
            if self.original_cwd:
                os.chdir(self.original_cwd)
                logger.info(f"Restored working directory after failed start: {self.original_cwd}")
                self.original_cwd = None
            return {"status": "error", "message": f"Failed to start GDB: {str(e)}"}

    def _is_gdb_alive(self) -> bool:
        """Check if the GDB process is still running."""
        if not self.controller:
            return False

        try:
            # Only check if this is a real GdbController with an actual subprocess.Popen
            # For tests with mocks, assume the process is alive
            if not hasattr(self.controller, "gdb_process"):
                return True

            gdb_process = self.controller.gdb_process

            # Check if this is actually a subprocess.Popen instance
            # If not (e.g., it's a Mock), assume alive to avoid breaking tests
            if not isinstance(gdb_process, subprocess.Popen):
                return True

            # Check if process is alive by checking its return code
            # poll() returns None if still running, or the exit code if exited
            poll_result = gdb_process.poll()
            if poll_result is not None:
                logger.error(f"GDB process exited with code {poll_result}")
            return poll_result is None
        except Exception as e:
            # If we can't check, assume alive to avoid false positives in tests
            logger.debug(f"Exception checking if GDB alive: {e}, assuming alive")
            return True

    def _send_command_and_wait_for_prompt(
        self, command: str, timeout_sec: float = DEFAULT_TIMEOUT_SEC
    ) -> dict[str, Any]:
        """
        Send a GDB/MI command with a token and wait for the (gdb) prompt.

        This method properly implements the GDB/MI protocol by:
        1. Sending commands with a unique token
        2. Reading responses until the (gdb) prompt appears
        3. Separating command responses (matching token) from async notifications

        Args:
            command: GDB/MI command to send (with or without '-' prefix)
            timeout_sec: Maximum time to wait for (gdb) prompt

        Returns:
            Dict with:
                - command_responses: list of responses matching the command token
                - async_notifications: list of async responses (no token or different token)
                - timed_out: bool indicating if we hit the timeout
        """
        import time

        if not self.controller:
            return {
                "command_responses": [],
                "async_notifications": [],
                "timed_out": True,
                "error": "No active GDB session",
            }

        # Get next token and increment counter
        token = self._command_token
        self._command_token += 1

        # Add token prefix to command
        tokenized_command = f"{token}{command}"

        logger.debug(f"Sending tokenized command: {tokenized_command}")

        # Write command to GDB without waiting for response
        # (we'll manually read until we see the prompt)
        try:
            self.controller.io_manager.stdin.write((tokenized_command + "\n").encode())
            self.controller.io_manager.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to send command: {e}")
            return {
                "command_responses": [],
                "async_notifications": [],
                "timed_out": False,
                "error": f"Failed to send command: {e}",
            }

        # Read responses until we see the (gdb) prompt
        # Timeout is based on inactivity, not total elapsed time
        # As long as GDB keeps producing output, we keep waiting
        command_responses: list[dict[str, Any]] = []
        async_notifications: list[dict[str, Any]] = []
        start_time = time.time()
        last_activity_time = start_time  # Track when we last received output
        last_alive_check = start_time

        while time.time() - last_activity_time < timeout_sec:
            # Check if GDB is alive periodically (every 1 second) to avoid overhead
            elapsed = time.time() - start_time
            if elapsed - last_alive_check >= 1.0:
                if not self._is_gdb_alive():
                    # Get the exit code for diagnostics
                    exit_code = None
                    try:
                        if hasattr(self.controller, "gdb_process") and isinstance(
                            self.controller.gdb_process, subprocess.Popen
                        ):
                            exit_code = self.controller.gdb_process.poll()
                    except Exception:
                        pass

                    error_details = f"GDB process exited unexpectedly after {elapsed:.1f}s"
                    if exit_code is not None:
                        if exit_code == -9:
                            error_details += " (exit code -9: killed, likely out of memory)"
                        elif exit_code == -6:
                            error_details += " (exit code -6: aborted, possibly assertion failure)"
                        elif exit_code == -11:
                            error_details += " (exit code -11: segmentation fault)"
                        else:
                            error_details += f" (exit code {exit_code})"

                    logger.error(error_details)
                    return {
                        "command_responses": command_responses,
                        "async_notifications": async_notifications,
                        "timed_out": False,
                        "error": error_details,
                    }
                last_alive_check = elapsed
                inactive_time = time.time() - last_activity_time
                logger.debug(
                    f"Still waiting for response... (total: {elapsed:.1f}s, inactive: {inactive_time:.1f}s)"
                )

            try:
                # Try to get responses with a short timeout
                responses = self.controller.get_gdb_response(
                    timeout_sec=POLL_TIMEOUT_SEC, raise_error_on_timeout=False
                )

                if not responses:
                    continue

                # Got responses - update last activity time
                last_activity_time = time.time()

                for response in responses:
                    response_type = response.get("type")
                    response_token = response.get("token")

                    logger.debug(
                        f"Received: type={response_type}, token={response_token}, message={response.get('message')}"
                    )

                    # Check for GDB internal fatal errors in console/log output
                    # These indicate GDB itself has crashed and won't recover
                    if response_type in ("console", "log"):
                        payload = response.get("payload", "")
                        payload_lower = payload.lower() if payload else ""
                        # Check for various fatal error messages from GDB
                        if payload and (
                            "internal-error" in payload_lower
                            or "fatal error internal to gdb" in payload_lower
                        ):
                            logger.error(f"GDB internal fatal error detected: {payload}")
                            # Stop the session immediately
                            if self.controller:
                                try:
                                    self.controller.exit()
                                except Exception:
                                    pass  # Best effort cleanup
                                self.controller = None
                                self.is_running = False
                                self.target_loaded = False

                            # Restore original working directory if it was changed
                            if self.original_cwd:
                                try:
                                    os.chdir(self.original_cwd)
                                    logger.info(
                                        f"Restored working directory after fatal error: {self.original_cwd}"
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to restore working directory: {e}")
                                self.original_cwd = None

                            return {
                                "command_responses": command_responses,
                                "async_notifications": async_notifications,
                                "timed_out": False,
                                "error": f"GDB internal fatal error: {payload.strip()}",
                                "fatal": True,
                            }

                    # According to GDB/MI spec, output is:
                    #   ( out-of-band-record )* [ result-record ] "(gdb)"
                    #
                    # When we send a command with token N:
                    # - We get various out-of-band records (console, notify, etc.)
                    #   These may have no token or different tokens
                    # - We get a result record with token N
                    # - Then we get (gdb) prompt (not exposed by pygdbmi)
                    #
                    # Since we operate synchronously (one command at a time),
                    # ALL responses between sending command and receiving result
                    # are part of this command's output.

                    # Check if this is the result record for our command
                    if response_type == "result" and response_token == token:
                        # Command complete - add result and return everything
                        command_responses.append(response)
                        logger.debug(f"Received result record for token {token}, command complete")
                        return {
                            "command_responses": command_responses,
                            "async_notifications": async_notifications,
                            "timed_out": False,
                        }

                    # This is output related to our command (or truly async)
                    # For synchronous operation, assume it's command output
                    if response_token == token or response_token is None:
                        command_responses.append(response)
                    else:
                        # Response with different token - truly async or from old command
                        async_notifications.append(response)
                        logger.info(
                            f"Async notification (token={response_token}): {response.get('message')} - {response.get('payload')}"
                        )

            except (BrokenPipeError, OSError) as e:
                logger.error(f"Communication error while reading responses: {e}")
                return {
                    "command_responses": command_responses,
                    "async_notifications": async_notifications,
                    "timed_out": False,
                    "error": f"Communication error: {e}",
                }

        # Timeout reached - GDB stopped producing output
        elapsed = time.time() - start_time
        logger.warning(f"Timeout: no GDB output for {timeout_sec}s (total elapsed: {elapsed:.1f}s)")
        return {
            "command_responses": command_responses,
            "async_notifications": async_notifications,
            "timed_out": True,
        }

    def execute_command(
        self, command: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC
    ) -> dict[str, Any]:
        """
        Execute a GDB command and return the parsed response.

        Uses the GDB/MI protocol properly by sending commands with tokens and waiting
        for the (gdb) prompt. Automatically handles both MI commands (starting with '-')
        and CLI commands. CLI commands are wrapped with -interpreter-exec for proper
        output capture.

        Args:
            command: GDB command to execute (MI or CLI command)
            timeout_sec: Timeout for command execution (default: 30s)

        Returns:
            Dict containing the command result and output
        """
        if not self.controller:
            return {"status": "error", "message": "No active GDB session"}

        # Check if GDB process is still alive before trying to send command
        if not self._is_gdb_alive():
            logger.error(f"GDB process is not running when trying to execute: {command}")
            return {
                "status": "error",
                "message": "GDB process has exited - cannot execute command",
                "command": command,
            }

        # Detect if this is a CLI command (doesn't start with '-')
        # CLI commands need to be wrapped with -interpreter-exec
        is_cli_command = not command.strip().startswith("-")
        actual_command = command

        if is_cli_command:
            # Escape backslashes and quotes in the command
            escaped_command = command.replace("\\", "\\\\").replace('"', '\\"')
            actual_command = f'-interpreter-exec console "{escaped_command}"'
            logger.debug(f"Wrapping CLI command: {command} -> {actual_command}")

        # Send command and wait for (gdb) prompt using the proper MI protocol
        result = self._send_command_and_wait_for_prompt(actual_command, timeout_sec)

        # Check for errors
        if "error" in result:
            error_response = {
                "status": "error",
                "message": result["error"],
                "command": command,
            }
            # Propagate fatal flag if present (indicates GDB internal error)
            if result.get("fatal"):
                error_response["fatal"] = True
            return error_response

        if result.get("timed_out"):
            return {
                "status": "error",
                "message": f"Timeout waiting for command response after {timeout_sec}s",
                "command": command,
            }

        # Parse command responses
        command_responses = result.get("command_responses", [])
        parsed = self._parse_responses(command_responses)

        # For CLI commands, format the output more clearly
        if is_cli_command:
            # Combine all console output
            console_output = "".join(parsed.get("console", []))

            return {
                "status": "success",
                "command": command,
                "output": console_output.strip() if console_output else "(no output)",
            }
        else:
            # For MI commands, return structured result
            return {"status": "success", "command": command, "result": parsed}

    def _parse_responses(self, responses: list[dict]) -> dict[str, Any]:
        """Parse GDB/MI responses into a structured format."""
        parsed: dict[str, Any] = {
            "console": [],
            "log": [],
            "output": [],
            "result": None,
            "notify": [],
        }

        for response in responses:
            msg_type = response.get("type")

            if msg_type == "console":
                console_list: list[Any] = parsed["console"]
                console_list.append(response.get("payload"))
            elif msg_type == "log":
                log_list: list[Any] = parsed["log"]
                log_list.append(response.get("payload"))
            elif msg_type == "output":
                output_list: list[Any] = parsed["output"]
                output_list.append(response.get("payload"))
            elif msg_type == "result":
                parsed["result"] = response.get("payload")
            elif msg_type == "notify":
                notify_list: list[Any] = parsed["notify"]
                notify_list.append(response.get("payload"))

        return parsed

    def _extract_mi_result(self, result: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Extract the MI result payload from a command response.

        GDB/MI commands return results in the format:
        {"status": "success", "result": {"result": {...actual data...}}}

        This helper extracts the inner "result" dictionary.

        Args:
            result: The command result dictionary

        Returns:
            The MI result payload, or None if not found
        """
        if result.get("status") != "success":
            return None
        inner_result: Optional[dict[str, Any]] = result.get("result", {}).get("result")
        return inner_result

    def get_threads(self) -> dict[str, Any]:
        """
        Get information about all threads in the debugged process.

        Returns:
            Dict with thread information
        """
        logger.debug("get_threads() called")
        result = self.execute_command("-thread-info")
        logger.debug(f"get_threads: execute_command returned: {result}")

        if result["status"] == "error":
            logger.debug(f"get_threads: returning error from execute_command")
            return result

        # Extract thread data from result
        # Use helper method but keep robust error handling for None cases
        thread_info = self._extract_mi_result(result)
        logger.debug(f"get_threads: thread_info type={type(thread_info)}, value={thread_info}")

        if thread_info is None:
            logger.warning("get_threads: thread_info is None - GDB returned incomplete data")
            return {
                "status": "error",
                "message": "GDB returned incomplete data - may still be loading symbols",
            }

        # Ensure thread_info is a dict (helper returns None if extraction fails)
        if not isinstance(thread_info, dict):
            thread_info = {}
        threads = thread_info.get("threads", [])
        current_thread = thread_info.get("current-thread-id")
        logger.debug(
            f"get_threads: found {len(threads)} threads, current_thread_id={current_thread}"
        )
        logger.debug(f"get_threads: threads data: {threads}")

        return {
            "status": "success",
            "threads": threads,
            "current_thread_id": current_thread,
            "count": len(threads),
        }

    def select_thread(self, thread_id: int) -> dict[str, Any]:
        """
        Select a specific thread to make it the current thread.

        Args:
            thread_id: Thread ID to select

        Returns:
            Dict with status and selected thread information
        """
        result = self.execute_command(f"-thread-select {thread_id}")

        if result["status"] == "error":
            return result

        mi_result = self._extract_mi_result(result) or {}

        return {
            "status": "success",
            "thread_id": thread_id,
            "new_thread_id": mi_result.get("new-thread-id"),
            "frame": mi_result.get("frame"),
        }

    def get_backtrace(
        self, thread_id: Optional[int] = None, max_frames: int = DEFAULT_MAX_BACKTRACE_FRAMES
    ) -> dict[str, Any]:
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

        stack_data = self._extract_mi_result(result) or {}
        frames = stack_data.get("stack", [])

        return {"status": "success", "thread_id": thread_id, "frames": frames, "count": len(frames)}

    def get_frame_info(self) -> dict[str, Any]:
        """
        Get information about the current stack frame.

        Returns:
            Dict with current frame information
        """
        result = self.execute_command("-stack-info-frame")

        if result["status"] == "error":
            return result

        mi_result = self._extract_mi_result(result) or {}
        frame = mi_result.get("frame", {})

        return {"status": "success", "frame": frame}

    def select_frame(self, frame_number: int) -> dict[str, Any]:
        """
        Select a specific stack frame to make it the current frame.

        Args:
            frame_number: Frame number (0 is innermost/current frame)

        Returns:
            Dict with status and frame information
        """
        result = self.execute_command(f"-stack-select-frame {frame_number}")

        if result["status"] == "error":
            return result

        # Get info about the selected frame
        frame_info_result = self.execute_command("-stack-info-frame")

        if frame_info_result["status"] == "error":
            return {
                "status": "success",
                "frame_number": frame_number,
                "message": f"Frame {frame_number} selected",
            }

        mi_result = self._extract_mi_result(frame_info_result) or {}
        frame_info = mi_result.get("frame", {})

        return {
            "status": "success",
            "frame_number": frame_number,
            "frame": frame_info,
        }

    def set_breakpoint(
        self, location: str, condition: Optional[str] = None, temporary: bool = False
    ) -> dict[str, Any]:
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
            # Escape backslashes and quotes in the condition
            escaped_condition = condition.replace("\\", "\\\\").replace('"', '\\"')
            cmd_parts.extend(["-c", f'"{escaped_condition}"'])

        cmd_parts.append(location)

        result = self.execute_command(" ".join(cmd_parts))

        if result["status"] == "error":
            return result

        # The MI result payload is in result["result"]["result"]
        # This contains the actual GDB/MI command result
        mi_result = self._extract_mi_result(result)

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

    def list_breakpoints(self) -> dict[str, Any]:
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
        mi_result = self._extract_mi_result(result) or {}

        # The MI response has a BreakpointTable with body containing array of bkpt objects
        bp_table = mi_result.get("BreakpointTable", {})
        breakpoints = bp_table.get("body", [])

        return {"status": "success", "breakpoints": breakpoints, "count": len(breakpoints)}

    def delete_breakpoint(self, number: int) -> dict[str, Any]:
        """
        Delete a breakpoint by its number.

        Args:
            number: Breakpoint number to delete

        Returns:
            Dict with status
        """
        result = self.execute_command(f"-break-delete {number}")

        if result["status"] == "error":
            return result

        return {"status": "success", "message": f"Breakpoint {number} deleted"}

    def enable_breakpoint(self, number: int) -> dict[str, Any]:
        """
        Enable a breakpoint by its number.

        Args:
            number: Breakpoint number to enable

        Returns:
            Dict with status
        """
        result = self.execute_command(f"-break-enable {number}")

        if result["status"] == "error":
            return result

        return {"status": "success", "message": f"Breakpoint {number} enabled"}

    def disable_breakpoint(self, number: int) -> dict[str, Any]:
        """
        Disable a breakpoint by its number.

        Args:
            number: Breakpoint number to disable

        Returns:
            Dict with status
        """
        result = self.execute_command(f"-break-disable {number}")

        if result["status"] == "error":
            return result

        return {"status": "success", "message": f"Breakpoint {number} disabled"}

    def run(self, args: Optional[list[str]] = None) -> dict[str, Any]:
        """
        Run the program (start execution from the beginning).

        Waits for the program to stop (at a breakpoint, signal, or exit) before
        returning. The (gdb) prompt indicates GDB is ready for subsequent commands.

        Args:
            args: Optional command-line arguments to pass to the program

        Returns:
            Dict with status and execution result
        """
        if not self.controller:
            return {"status": "error", "message": "No active GDB session"}

        # Set program arguments if provided
        if args:
            arg_str = " ".join(args)
            result = self.execute_command(f"-exec-arguments {arg_str}")
            if result.get("status") == "error":
                return result

        # Run the program - execute_command waits for (gdb) prompt
        return self.execute_command("-exec-run")

    def continue_execution(self) -> dict[str, Any]:
        """
        Continue execution of the program.

        Waits for the program to stop (at a breakpoint, signal, or exit) before
        returning. The (gdb) prompt indicates GDB is ready for subsequent commands.

        Returns:
            Dict with status and execution result
        """
        return self.execute_command("-exec-continue")

    def step(self) -> dict[str, Any]:
        """
        Step into (single source line, entering functions).

        Waits for the step to complete before returning. The (gdb) prompt indicates
        GDB is ready for subsequent commands.

        Returns:
            Dict with status and execution result
        """
        return self.execute_command("-exec-step")

    def next(self) -> dict[str, Any]:
        """
        Step over (next source line, not entering functions).

        Waits for the step to complete before returning. The (gdb) prompt indicates
        GDB is ready for subsequent commands.

        Returns:
            Dict with status and execution result
        """
        return self.execute_command("-exec-next")

    def interrupt(self) -> dict[str, Any]:
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

            # Poll for *stopped notification with timeout
            # This avoids arbitrary sleep and responds as soon as GDB confirms the stop
            start_time = time.time()
            all_responses: list[dict[str, Any]] = []
            stopped_received = False

            while time.time() - start_time < INTERRUPT_RESPONSE_TIMEOUT_SEC:
                responses = self.controller.get_gdb_response(
                    timeout_sec=POLL_TIMEOUT_SEC, raise_error_on_timeout=False
                )

                if responses:
                    all_responses.extend(responses)
                    # Check for *stopped notification
                    for resp in responses:
                        if resp.get("type") == "notify" and resp.get("message") == "stopped":
                            stopped_received = True
                            break

                if stopped_received:
                    break

            result = self._parse_responses(all_responses)

            if not stopped_received:
                return {
                    "status": "warning",
                    "message": "Interrupt sent but no stopped notification received",
                    "result": result,
                }

            return {
                "status": "success",
                "message": "Program interrupted (paused)",
                "result": result,
            }
        except Exception as e:
            logger.error(f"Failed to interrupt program: {e}")
            return {"status": "error", "message": f"Failed to interrupt: {str(e)}"}

    def evaluate_expression(self, expression: str) -> dict[str, Any]:
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

        mi_result = self._extract_mi_result(result) or {}
        value = mi_result.get("value")

        return {"status": "success", "expression": expression, "value": value}

    def get_variables(self, thread_id: Optional[int] = None, frame: int = 0) -> dict[str, Any]:
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
            thread_result = self.execute_command(f"-thread-select {thread_id}")
            if thread_result.get("status") == "error":
                return thread_result

        # Select frame
        frame_result = self.execute_command(f"-stack-select-frame {frame}")
        if frame_result.get("status") == "error":
            return frame_result

        # Get variables
        result = self.execute_command("-stack-list-variables --simple-values")

        if result["status"] == "error":
            return result

        mi_result = self._extract_mi_result(result) or {}
        variables = mi_result.get("variables", [])

        return {"status": "success", "thread_id": thread_id, "frame": frame, "variables": variables}

    def get_registers(self) -> dict[str, Any]:
        """Get register values for current frame."""
        result = self.execute_command("-data-list-register-values x")

        if result["status"] == "error":
            return result

        mi_result = self._extract_mi_result(result) or {}
        registers = mi_result.get("register-values", [])

        return {"status": "success", "registers": registers}

    def stop(self) -> dict[str, Any]:
        """Stop the GDB session."""
        if not self.controller:
            return {"status": "error", "message": "No active session"}

        try:
            self.controller.exit()
            self.controller = None
            self.is_running = False
            self.target_loaded = False

            # Restore original working directory if it was changed during start()
            if self.original_cwd:
                os.chdir(self.original_cwd)
                logger.info(f"Restored working directory to: {self.original_cwd}")
                self.original_cwd = None

            return {"status": "success", "message": "GDB session stopped"}

        except Exception as e:
            logger.error(f"Failed to stop GDB session: {e}")
            # Still try to restore working directory even if stop failed
            if self.original_cwd:
                try:
                    os.chdir(self.original_cwd)
                    logger.info(f"Restored working directory after error: {self.original_cwd}")
                    self.original_cwd = None
                except Exception as cwd_error:
                    logger.warning(f"Failed to restore working directory: {cwd_error}")
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the GDB session."""
        return {
            "is_running": self.is_running,
            "target_loaded": self.target_loaded,
            "has_controller": self.controller is not None,
        }

    def call_function(
        self, function_call: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC
    ) -> dict[str, Any]:
        """
        Call a function in the target process.

        This is a privileged operation that executes the GDB 'call' command,
        which invokes a function in the debugged program. This can execute
        arbitrary code in the target process and may have side effects.

        WARNING: Use with caution as this can modify program state.

        Args:
            function_call: Function call expression (e.g., "printf(\\"hello\\n\\")"
                          or "my_function(arg1, arg2)")
            timeout_sec: Timeout for command execution

        Returns:
            Dict with the function's return value or error
        """
        if not self.controller:
            return {"status": "error", "message": "No active GDB session"}

        if not self._is_gdb_alive():
            return {
                "status": "error",
                "message": "GDB process has exited - cannot execute call",
            }

        # Build the call command
        command = f"call {function_call}"

        # Escape for MI command
        escaped_command = command.replace("\\", "\\\\").replace('"', '\\"')
        mi_command = f'-interpreter-exec console "{escaped_command}"'

        result = self._send_command_and_wait_for_prompt(mi_command, timeout_sec)

        if "error" in result:
            return {
                "status": "error",
                "message": result["error"],
                "function_call": function_call,
            }

        if result.get("timed_out"):
            return {
                "status": "error",
                "message": f"Timeout waiting for call to complete after {timeout_sec}s",
                "function_call": function_call,
            }

        parsed = self._parse_responses(result.get("command_responses", []))
        console_output = "".join(parsed.get("console", []))

        return {
            "status": "success",
            "function_call": function_call,
            "result": console_output.strip() if console_output else "(no return value)",
        }
