"""MCP Server for GDB debugging interface."""

import asyncio
import json
import logging
import os
import threading
from typing import Any, Optional
from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field
from .gdb_interface import GDBSession

# Set up logging - use GDB_MCP_LOG_LEVEL environment variable
log_level = os.environ.get("GDB_MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages multiple GDB debugging sessions.

    Thread-safe session management with simple integer session IDs.
    Sessions are created, retrieved by ID, and explicitly removed.
    """

    def __init__(self):
        """Initialize the session manager with empty session storage."""
        self._sessions: dict[int, GDBSession] = {}
        self._next_session_id: int = 1
        self._lock = threading.Lock()

    def create_session(self) -> int:
        """
        Create a new GDB session and return its unique session ID.

        Returns:
            Integer session ID (starts at 1, monotonically increasing)
        """
        with self._lock:
            session_id = self._next_session_id
            self._next_session_id += 1
            self._sessions[session_id] = GDBSession()
        return session_id

    def get_session(self, session_id: int) -> Optional[GDBSession]:
        """
        Retrieve a GDB session by its ID.

        Args:
            session_id: The session ID to look up

        Returns:
            GDBSession instance if found, None otherwise
        """
        with self._lock:
            return self._sessions.get(session_id)

    def remove_session(self, session_id: int) -> bool:
        """
        Remove a GDB session by its ID.

        Args:
            session_id: The session ID to remove

        Returns:
            True if session was removed, False if it didn't exist
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False


# Global session manager instance
session_manager = SessionManager()

# Create MCP server instance
app = Server("gdb-mcp-server")


# Tool argument models
class StartSessionArgs(BaseModel):
    program: Optional[str] = Field(None, description="Path to executable to debug")
    args: Optional[list[str]] = Field(None, description="Command-line arguments for the program")
    init_commands: Optional[list[str]] = Field(
        None,
        description="GDB commands to run on startup (e.g., 'core-file /path/to/core', 'set sysroot /path')",
    )
    env: Optional[dict[str, str]] = Field(
        None,
        description="Environment variables to set for the debugged program (e.g., {'LD_LIBRARY_PATH': '/custom/libs'})",
    )
    gdb_path: Optional[str] = Field(
        None,
        description="Path to GDB executable (default: from GDB_PATH env var or 'gdb')",
    )
    working_dir: Optional[str] = Field(
        None,
        description=(
            "Working directory to use when starting GDB. "
            "Use this when debugging programs that need to be run from a specific directory, "
            "or when the program expects to find files (config, data, etc.) relative to its working directory. "
            "GDB will be started in this directory, then the original directory is restored. "
            "Example: If debugging a server that loads config from './config.json', set working_dir to the server's directory."
        ),
    )
    core: Optional[str] = Field(
        None,
        description=(
            "Path to core dump file for post-mortem debugging. "
            "When specified, GDB is started with --core flag which properly initializes symbol resolution. "
            "IMPORTANT: When using a sysroot with core dumps, set sysroot AFTER the core is loaded "
            "(either via this parameter or core-file command) for symbols to resolve correctly."
        ),
    )


class ExecuteCommandArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    command: str = Field(..., description="GDB command to execute")


class GetBacktraceArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    thread_id: Optional[int] = Field(None, description="Thread ID (None for current thread)")
    max_frames: int = Field(100, description="Maximum number of frames to retrieve")


class SetBreakpointArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    location: str = Field(..., description="Breakpoint location (function, file:line, or *address)")
    condition: Optional[str] = Field(None, description="Conditional expression")
    temporary: bool = Field(False, description="Whether breakpoint is temporary")


class EvaluateExpressionArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    expression: str = Field(..., description="C/C++ expression to evaluate")


class GetVariablesArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    thread_id: Optional[int] = Field(None, description="Thread ID (None for current)")
    frame: int = Field(0, description="Frame number (0 is current)")


class ThreadSelectArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    thread_id: int = Field(..., description="Thread ID to select")


class BreakpointNumberArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    number: int = Field(..., description="Breakpoint number")


class FrameSelectArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    frame_number: int = Field(..., description="Frame number (0 is current/innermost frame)")


class CallFunctionArgs(BaseModel):
    session_id: int = Field(..., description="Session ID from gdb_start_session")
    function_call: str = Field(
        ...,
        description="Function call expression (e.g., 'printf(\"hello\\n\")' or 'my_func(arg1, arg2)')",
    )


class SessionIdArgs(BaseModel):
    """Arguments for tools that only need session_id."""

    session_id: int = Field(..., description="Session ID from gdb_start_session")


# List available tools
@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available GDB debugging tools."""
    return [
        Tool(
            name="gdb_start_session",
            description=(
                "Start a new GDB debugging session. Can load an executable, core dump, "
                "or run custom initialization commands. "
                "Automatically detects and reports important warnings such as: "
                "missing debug symbols (not compiled with -g), file not found, or invalid executable. "
                "Check the 'warnings' field in the response for critical issues that may affect debugging. "
                "Available parameters: program (executable path), args (program arguments), "
                "core (core dump path - uses --core flag for proper symbol resolution), "
                "init_commands (GDB commands to run after loading), "
                "env (environment variables), gdb_path (GDB binary path), "
                "working_dir (directory to run program from). "
                "IMPORTANT for core dump debugging: Set 'sysroot' and 'solib-search-path' AFTER "
                "loading the core (either via 'core' parameter or 'core-file' init_command) "
                "for symbols to resolve correctly. "
                "Returns a session_id integer that must be passed to all other GDB tools."
            ),
            inputSchema=StartSessionArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_execute_command",
            description=(
                "Execute a GDB command. Supports both CLI and MI commands. "
                "CLI commands (like 'info breakpoints', 'list', 'print x') are automatically "
                "handled and their output is formatted for readability. "
                "MI commands (starting with '-', like '-break-list', '-exec-run') return "
                "structured data. "
                "NOTE: For calling functions in the target process, prefer using the dedicated "
                "gdb_call_function tool instead of 'call' command, as it provides better "
                "structured output and can be separately permissioned. "
                "Common examples: 'info breakpoints', 'info threads', 'run', 'print variable', "
                "'list main', 'disassemble func'. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=ExecuteCommandArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_status",
            description=(
                "Get the current status of the GDB session. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_threads",
            description=(
                "Get information about all threads in the debugged process, including "
                "thread IDs, states, and the current thread. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_select_thread",
            description=(
                "Select a specific thread to make it the current thread. "
                "After selecting a thread, subsequent commands like gdb_get_backtrace, "
                "gdb_get_variables, and gdb_evaluate_expression will operate on this thread. "
                "Use gdb_get_threads to see available thread IDs. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=ThreadSelectArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_backtrace",
            description=(
                "Get the stack backtrace for a specific thread or the current thread. "
                "Shows function calls, file locations, and line numbers. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=GetBacktraceArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_select_frame",
            description=(
                "Select a specific stack frame to make it the current frame. "
                "Frame 0 is the innermost (current) frame, higher numbers are outer frames. "
                "After selecting a frame, commands like gdb_get_variables and gdb_evaluate_expression "
                "will operate in the context of that frame. "
                "Use gdb_get_backtrace to see available frames and their numbers. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=FrameSelectArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_frame_info",
            description=(
                "Get information about the current stack frame. "
                "Returns details about the currently selected frame including function name, "
                "file location, line number, and address. "
                "Use gdb_select_frame to change the current frame first if needed. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_set_breakpoint",
            description=(
                "Set a breakpoint at a function, file:line, or address. "
                "Supports conditional breakpoints and temporary breakpoints. "
                "Returns breakpoint details including number, address, and location. "
                "Use gdb_list_breakpoints to verify breakpoints were set correctly. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SetBreakpointArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_list_breakpoints",
            description=(
                "List all breakpoints as structured data with detailed information. "
                "Returns an array of breakpoint objects, each containing: number, type, "
                "enabled status, address, function name, source file, line number, and hit count. "
                "Use this to verify breakpoints were set correctly, check which have been hit "
                "(times field), and inspect their exact locations. "
                "Much easier to filter and analyze than text output. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_delete_breakpoint",
            description=(
                "Delete a breakpoint by its number. "
                "Use gdb_list_breakpoints to see breakpoint numbers. "
                "Once deleted, the breakpoint cannot be recovered. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=BreakpointNumberArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_enable_breakpoint",
            description=(
                "Enable a previously disabled breakpoint by its number. "
                "Enabled breakpoints will pause execution when hit. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=BreakpointNumberArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_disable_breakpoint",
            description=(
                "Disable a breakpoint by its number without deleting it. "
                "Disabled breakpoints are not hit but remain in the breakpoint list. "
                "Use gdb_enable_breakpoint to re-enable it later. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=BreakpointNumberArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_continue",
            description=(
                "Continue execution of the program until next breakpoint or completion. "
                "IMPORTANT: Only use this when the program is PAUSED (e.g., at a breakpoint). "
                "If the program hasn't been started yet, use gdb_execute_command with 'run' instead. "
                "If the program is already running, this will fail - use gdb_interrupt to pause it first. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_step",
            description=(
                "Step into the next instruction (enters function calls). "
                "IMPORTANT: Only works when program is PAUSED at a specific location. "
                "Use this for single-stepping through code to debug line-by-line. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_next",
            description=(
                "Step over to the next line (doesn't enter function calls). "
                "IMPORTANT: Only works when program is PAUSED at a specific location. "
                "Use this to step over function calls without entering them. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_interrupt",
            description=(
                "Interrupt (pause) a running program. Use this when: "
                "1) The program is running and hasn't hit a breakpoint, "
                "2) You want to pause execution to inspect state or set breakpoints, "
                "3) The program appears stuck or you want to see where it is. "
                "After interrupting, you can use other commands like gdb_get_backtrace, "
                "gdb_get_variables, or gdb_continue. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_evaluate_expression",
            description=(
                "Evaluate a C/C++ expression in the current context and return its value. "
                "Can access variables, dereference pointers, call functions, etc. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=EvaluateExpressionArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_variables",
            description=(
                "Get local variables for a specific stack frame in a thread. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=GetVariablesArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_registers",
            description=(
                "Get CPU register values for the current frame. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_stop_session",
            description=(
                "Stop the current GDB session and clean up resources. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=SessionIdArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_call_function",
            description=(
                "Call a function in the target process. "
                "WARNING: This is a privileged operation that executes code in the debugged program. "
                "It can call any function accessible in the current context, including: "
                "- Standard library functions: printf, malloc, free, etc. "
                "- Program functions: any function defined in the program "
                "- System calls via wrappers "
                "The function executes with full privileges of the debugged process. "
                "Use with caution as it may have side effects and modify program state. "
                "Examples: 'printf(\"debug: x=%d\\n\", x)', 'my_cleanup_func()', 'strlen(str)'. "
                "Requires session_id parameter (obtained from gdb_start_session)."
            ),
            inputSchema=CallFunctionArgs.model_json_schema(),
        ),
    ]


# Tool implementations
@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls from the MCP client."""

    try:
        if name == "gdb_start_session":
            args = StartSessionArgs(**arguments)
            session_id = session_manager.create_session()
            session = session_manager.get_session(session_id)

            if session is None:
                raise RuntimeError(f"Failed to create session {session_id}")

            result = session.start(
                program=args.program,
                args=args.args,
                init_commands=args.init_commands,
                env=args.env,
                gdb_path=args.gdb_path,
                working_dir=args.working_dir,
                core=args.core,
            )
            result["session_id"] = session_id

        else:
            session_id = arguments.get("session_id")
            session = session_manager.get_session(session_id)

            if session is None:
                result = {
                    "status": "error",
                    "message": f"Invalid session_id: {session_id}. Use gdb_start_session to create a new session.",
                }
            elif name == "gdb_execute_command":
                exec_args: ExecuteCommandArgs = ExecuteCommandArgs(**arguments)
                result = session.execute_command(command=exec_args.command)

            elif name == "gdb_get_status":
                result = session.get_status()

            elif name == "gdb_get_threads":
                result = session.get_threads()

            elif name == "gdb_select_thread":
                thread_args: ThreadSelectArgs = ThreadSelectArgs(**arguments)
                result = session.select_thread(thread_id=thread_args.thread_id)

            elif name == "gdb_get_backtrace":
                backtrace_args: GetBacktraceArgs = GetBacktraceArgs(**arguments)
                result = session.get_backtrace(
                    thread_id=backtrace_args.thread_id,
                    max_frames=backtrace_args.max_frames,
                )

            elif name == "gdb_select_frame":
                frame_args: FrameSelectArgs = FrameSelectArgs(**arguments)
                result = session.select_frame(frame_number=frame_args.frame_number)

            elif name == "gdb_get_frame_info":
                result = session.get_frame_info()

            elif name == "gdb_set_breakpoint":
                bp_args: SetBreakpointArgs = SetBreakpointArgs(**arguments)
                result = session.set_breakpoint(
                    location=bp_args.location,
                    condition=bp_args.condition,
                    temporary=bp_args.temporary,
                )

            elif name == "gdb_list_breakpoints":
                result = session.list_breakpoints()

            elif name == "gdb_delete_breakpoint":
                del_bp_args: BreakpointNumberArgs = BreakpointNumberArgs(**arguments)
                result = session.delete_breakpoint(number=del_bp_args.number)

            elif name == "gdb_enable_breakpoint":
                en_bp_args: BreakpointNumberArgs = BreakpointNumberArgs(**arguments)
                result = session.enable_breakpoint(number=en_bp_args.number)

            elif name == "gdb_disable_breakpoint":
                dis_bp_args: BreakpointNumberArgs = BreakpointNumberArgs(**arguments)
                result = session.disable_breakpoint(number=dis_bp_args.number)

            elif name == "gdb_continue":
                result = session.continue_execution()

            elif name == "gdb_step":
                result = session.step()

            elif name == "gdb_next":
                result = session.next()

            elif name == "gdb_interrupt":
                result = session.interrupt()

            elif name == "gdb_evaluate_expression":
                eval_args: EvaluateExpressionArgs = EvaluateExpressionArgs(**arguments)
                result = session.evaluate_expression(eval_args.expression)

            elif name == "gdb_get_variables":
                var_args: GetVariablesArgs = GetVariablesArgs(**arguments)
                result = session.get_variables(thread_id=var_args.thread_id, frame=var_args.frame)

            elif name == "gdb_get_registers":
                result = session.get_registers()

            elif name == "gdb_stop_session":
                result = session.stop()
                session_manager.remove_session(session_id)

            elif name == "gdb_call_function":
                call_args: CallFunctionArgs = CallFunctionArgs(**arguments)
                result = session.call_function(function_call=call_args.function_call)

            else:
                result = {"status": "error", "message": f"Unknown tool: {name}"}

        result_text = json.dumps(result, indent=2)
        return [TextContent(type="text", text=result_text)]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        error_result = {"status": "error", "message": str(e), "tool": name}
        return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def main():
    """Main async entry point for the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        logger.info("GDB MCP Server starting...")
        await app.run(read_stream, write_stream, app.create_initialization_options())


def run_server():
    """Synchronous entry point for the MCP server (for script entry point)."""
    asyncio.run(main())


if __name__ == "__main__":
    run_server()
