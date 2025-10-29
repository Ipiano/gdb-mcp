"""MCP Server for GDB debugging interface."""

import asyncio
import logging
from typing import Any, Optional
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from pydantic import BaseModel, Field
from .gdb_interface import GDBSession

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global GDB session instance
gdb_session = GDBSession()

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
    gdb_path: str = Field("gdb", description="Path to GDB executable (default: 'gdb')")
    init_timeout_sec: int = Field(
        30,
        description="Timeout for initialization in seconds (default: 30s, covers init commands and readiness polling)",
    )


class ExecuteCommandArgs(BaseModel):
    command: str = Field(..., description="GDB command to execute")
    timeout_sec: int = Field(5, description="Timeout in seconds")


class StopSessionArgs(BaseModel):
    timeout_sec: int = Field(
        5,
        description="Timeout for graceful GDB exit in seconds (default: 5s, GDB will be force-killed if it doesn't exit in time)",
    )


class LoadFileArgs(BaseModel):
    file_path: str = Field(..., description="Path to the file to load")
    file_type: str = Field(
        "auto",
        description="Type of file: 'executable', 'core', 'symbols', or 'auto' (default: auto-detect)",
    )
    timeout_sec: int = Field(
        60,
        description="Timeout for loading and readiness check in seconds (default: 60s)",
    )


class GetBacktraceArgs(BaseModel):
    thread_id: Optional[int] = Field(None, description="Thread ID (None for current thread)")
    max_frames: int = Field(100, description="Maximum number of frames to retrieve")


class SetBreakpointArgs(BaseModel):
    location: str = Field(..., description="Breakpoint location (function, file:line, or *address)")
    condition: Optional[str] = Field(None, description="Conditional expression")
    temporary: bool = Field(False, description="Whether breakpoint is temporary")


class EvaluateExpressionArgs(BaseModel):
    expression: str = Field(..., description="C/C++ expression to evaluate")


class GetVariablesArgs(BaseModel):
    thread_id: Optional[int] = Field(None, description="Thread ID (None for current)")
    frame: int = Field(0, description="Frame number (0 is current)")


class ThreadSelectArgs(BaseModel):
    thread_id: int = Field(..., description="Thread ID to select")


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
                "The session waits for GDB to be fully ready before returning, preventing NoneType errors. "
                "Automatically detects and reports important warnings such as: "
                "missing debug symbols (not compiled with -g), file not found, or invalid executable. "
                "Check the 'warnings' field in the response for critical issues that may affect debugging. "
                "For large core dumps or cross-architecture debugging, increase 'init_timeout_sec' "
                "(default 30s) to allow time for symbol loading and readiness. "
                "Examples of init_commands: 'core-file /path/to/core', 'set sysroot /path', "
                "'set solib-search-path /path'"
            ),
            inputSchema=StartSessionArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_execute_command",
            description=(
                "Execute any GDB command directly. Supports both CLI and MI commands. "
                "CLI commands (like 'info breakpoints', 'list', 'print x') are automatically "
                "handled and their output is formatted for readability. "
                "MI commands (starting with '-', like '-break-list', '-exec-run') return "
                "structured data. Use this for: "
                "1) Commands not covered by specialized tools (info, show, set, etc.), "
                "2) Starting programs ('run', 'start'), "
                "3) Advanced GDB operations. "
                "Common examples: 'info breakpoints', 'info threads', 'run', 'print variable', "
                "'list main', 'disassemble func'."
            ),
            inputSchema=ExecuteCommandArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_status",
            description="Get the current status of the GDB session.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_get_threads",
            description=(
                "Get information about all threads in the debugged process, including "
                "thread IDs, states, and the current thread."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_get_backtrace",
            description=(
                "Get the stack backtrace for a specific thread or the current thread. "
                "Shows function calls, file locations, and line numbers."
            ),
            inputSchema=GetBacktraceArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_set_breakpoint",
            description=(
                "Set a breakpoint at a function, file:line, or address. "
                "Supports conditional breakpoints and temporary breakpoints. "
                "Returns breakpoint details including number, address, and location. "
                "Use gdb_list_breakpoints to verify breakpoints were set correctly."
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
                "Much easier to filter and analyze than text output."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_continue",
            description=(
                "Continue execution of the program until next breakpoint or completion. "
                "IMPORTANT: Only use this when the program is PAUSED (e.g., at a breakpoint). "
                "If the program hasn't been started yet, use gdb_execute_command with 'run' instead. "
                "If the program is already running, this will fail - use gdb_interrupt to pause it first."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_step",
            description=(
                "Step into the next instruction (enters function calls). "
                "IMPORTANT: Only works when program is PAUSED at a specific location. "
                "Use this for single-stepping through code to debug line-by-line."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_next",
            description=(
                "Step over to the next line (doesn't enter function calls). "
                "IMPORTANT: Only works when program is PAUSED at a specific location. "
                "Use this to step over function calls without entering them."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_interrupt",
            description=(
                "Interrupt (pause) a running program. Use this when: "
                "1) The program is running and hasn't hit a breakpoint, "
                "2) You want to pause execution to inspect state or set breakpoints, "
                "3) The program appears stuck or you want to see where it is. "
                "After interrupting, you can use other commands like gdb_get_backtrace, "
                "gdb_get_variables, or gdb_continue."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_evaluate_expression",
            description=(
                "Evaluate a C/C++ expression in the current context and return its value. "
                "Can access variables, dereference pointers, call functions, etc."
            ),
            inputSchema=EvaluateExpressionArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_variables",
            description="Get local variables for a specific stack frame in a thread.",
            inputSchema=GetVariablesArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_get_registers",
            description="Get CPU register values for the current frame.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gdb_stop_session",
            description=(
                "Stop the current GDB session and clean up resources. "
                "Uses a timeout to prevent hanging - if GDB doesn't exit gracefully, it will be force-killed. "
                "Session state is always cleaned up, allowing immediate start of a new session."
            ),
            inputSchema=StopSessionArgs.model_json_schema(),
        ),
        Tool(
            name="gdb_load_file",
            description=(
                "Load a file (executable, core dump, or symbol file) and wait for GDB to be ready. "
                "This is the PREFERRED way to load core dumps or executables after starting a session, "
                "as it includes automatic readiness polling to ensure GDB has finished all background "
                "symbol loading and processing before returning. "
                "Detects GDB crashes during loading and returns a clear error. "
                "For large core dumps or cross-architecture debugging, increase timeout_sec (default 60s). "
                "File types: 'executable' (loads binary), 'core' (loads core dump), "
                "'symbols' (loads symbol file), 'auto' (auto-detect from filename). "
                "Use this instead of 'gdb_execute_command' with 'core-file' or 'file' commands "
                "to avoid NoneType errors and timeouts."
            ),
            inputSchema=LoadFileArgs.model_json_schema(),
        ),
    ]


# Tool implementations
@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls from the MCP client."""

    try:
        if name == "gdb_start_session":
            args = StartSessionArgs(**arguments)
            result = gdb_session.start(
                program=args.program,
                args=args.args,
                init_commands=args.init_commands,
                env=args.env,
                gdb_path=args.gdb_path,
                init_timeout_sec=args.init_timeout_sec,
            )

        elif name == "gdb_execute_command":
            args = ExecuteCommandArgs(**arguments)
            result = gdb_session.execute_command(command=args.command, timeout_sec=args.timeout_sec)

        elif name == "gdb_get_status":
            result = gdb_session.get_status()

        elif name == "gdb_get_threads":
            result = gdb_session.get_threads()

        elif name == "gdb_get_backtrace":
            args = GetBacktraceArgs(**arguments)
            result = gdb_session.get_backtrace(thread_id=args.thread_id, max_frames=args.max_frames)

        elif name == "gdb_set_breakpoint":
            args = SetBreakpointArgs(**arguments)
            result = gdb_session.set_breakpoint(
                location=args.location, condition=args.condition, temporary=args.temporary
            )

        elif name == "gdb_list_breakpoints":
            result = gdb_session.list_breakpoints()

        elif name == "gdb_continue":
            result = gdb_session.continue_execution()

        elif name == "gdb_step":
            result = gdb_session.step()

        elif name == "gdb_next":
            result = gdb_session.next()

        elif name == "gdb_interrupt":
            result = gdb_session.interrupt()

        elif name == "gdb_evaluate_expression":
            args = EvaluateExpressionArgs(**arguments)
            result = gdb_session.evaluate_expression(args.expression)

        elif name == "gdb_get_variables":
            args = GetVariablesArgs(**arguments)
            result = gdb_session.get_variables(thread_id=args.thread_id, frame=args.frame)

        elif name == "gdb_get_registers":
            result = gdb_session.get_registers()

        elif name == "gdb_stop_session":
            args = StopSessionArgs(**arguments)
            result = gdb_session.stop(timeout_sec=args.timeout_sec)

        elif name == "gdb_load_file":
            args = LoadFileArgs(**arguments)
            result = gdb_session.load_file(
                file_path=args.file_path,
                file_type=args.file_type,
                timeout_sec=args.timeout_sec,
            )

        else:
            result = {"status": "error", "message": f"Unknown tool: {name}"}

        # Format result as text
        import json

        result_text = json.dumps(result, indent=2)

        return [TextContent(type="text", text=result_text)]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}", exc_info=True)
        import json

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
