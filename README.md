# GDB MCP Server

An MCP (Model Context Protocol) server that provides AI assistants with programmatic access to GDB debugging sessions. This allows AI models to interact with debuggers in the same way IDEs like VS Code and CLion do, using the GDB/MI (Machine Interface) protocol.

## Features

- **Full GDB Control**: Start sessions, execute commands, control program execution
- **Thread Analysis**: Inspect threads, get backtraces, analyze thread states
- **Breakpoint Management**: Set conditional breakpoints, temporary breakpoints
- **Variable Inspection**: Evaluate expressions, inspect variables and registers
- **Core Dump Analysis**: Load and analyze core dumps with custom initialization
- **Flexible Initialization**: Run GDB scripts or commands on startup

## Architecture

This server uses the **GDB/MI (Machine Interface)** protocol, which is the same interface used by professional IDEs. It provides:

- Structured, machine-parseable output
- Async notifications for state changes
- Full access to GDB's debugging capabilities
- Reliable command execution and response handling

## Installation

### Prerequisites

- Python 3.10 or higher
- GDB installed and available in PATH

### Quick Start

**Recommended: Using pipx** (simplest, no path management needed):
```bash
# Install pipx if needed
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install gdb-mcp-server
cd /path/to/gdb-mcp
pipx install .
```

**Alternative: Using virtual environment**:
```bash
cd /path/to/gdb-mcp
./setup-venv.sh  # Linux/macOS
# or
setup-venv.bat   # Windows
```

**For detailed installation instructions, troubleshooting, and other installation methods, see [INSTALL.md](INSTALL.md).**

## Configuration

### Claude Desktop

Add this to your Claude Desktop configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `~/.config/Claude/claude_desktop_config.json` on Linux, or `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

**If installed with pipx:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

**If using virtual environment:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "/absolute/path/to/gdb-mcp/venv/bin/python",
      "args": ["-m", "gdb_mcp"]
    }
  }
}
```

**For detailed configuration examples and other MCP clients, see [INSTALL.md](INSTALL.md#step-5-configure-your-mcp-client).**

## Available Tools

### Session Management

#### `gdb_start_session`
Start a new GDB debugging session.

**Parameters:**
- `program` (optional): Path to executable to debug
- `args` (optional): Command-line arguments for the program
- `init_commands` (optional): List of GDB commands to run on startup

**Returns:**
- `status`: "success" or "error"
- `message`: Status message
- `program`: Program path
- `startup_output` (optional): GDB's initial output when loading the program
- `warnings` (optional): Array of critical warnings detected, such as:
  - "No debugging symbols found - program was not compiled with -g"
  - "File is not an executable"
  - "Program file not found"
- `init_output` (optional): Output from init_commands if provided

**Important:** Always check the `warnings` field! Missing debug symbols will prevent breakpoints from working and variable inspection from showing useful information.

**Example init_commands:**
```python
[
    "file /path/to/executable",
    "core-file /path/to/core.dump",
    "set sysroot /path/to/sysroot",
    "set solib-search-path /path/to/libs"
]
```

#### `gdb_execute_command`
Execute any GDB command directly. Supports both CLI and MI commands.

**Parameters:**
- `command`: GDB command to execute (CLI or MI format)
- `timeout_sec`: Timeout in seconds (default: 5)

**Automatically handles two types of commands:**

1. **CLI Commands** (traditional GDB commands):
   - Examples: `info breakpoints`, `list`, `print x`, `run`, `backtrace`
   - Output is formatted as readable text
   - These are the commands you'd type in interactive GDB

2. **MI Commands** (Machine Interface commands, start with `-`):
   - Examples: `-break-list`, `-exec-run`, `-data-evaluate-expression`
   - Return structured data
   - More precise but less human-readable

**Common CLI commands:**
- `info breakpoints` - List all breakpoints
- `info threads` - List all threads
- `run` - Start the program
- `print variable` - Print a variable's value
- `backtrace` - Show call stack
- `list` - Show source code
- `disassemble` - Show assembly code

#### `gdb_get_status`
Get the current status of the GDB session.

#### `gdb_stop_session`
Stop the current GDB session.

### Thread Inspection

#### `gdb_get_threads`
Get information about all threads in the debugged process.

**Returns:**
- List of threads with IDs and states
- Current thread ID
- Thread count

#### `gdb_get_backtrace`
Get stack backtrace for a thread.

**Parameters:**
- `thread_id` (optional): Thread ID (None for current thread)
- `max_frames`: Maximum frames to retrieve (default: 100)

### Breakpoints and Execution Control

#### `gdb_set_breakpoint`
Set a breakpoint at a location.

**Parameters:**
- `location`: Function name, file:line, or *address
- `condition` (optional): Conditional expression
- `temporary`: Whether breakpoint is temporary (default: false)

**Examples:**
- `location: "main"` - Break at main function
- `location: "foo.c:42"` - Break at line 42 of foo.c
- `location: "*0x12345678"` - Break at memory address
- `condition: "x > 10"` - Only break when x > 10

#### `gdb_list_breakpoints`
List all breakpoints with structured data.

**Returns:**
- `status`: "success" or "error"
- `breakpoints`: Array of breakpoint objects
- `count`: Total number of breakpoints

**Each breakpoint object contains:**
- `number`: Breakpoint number (string)
- `type`: "breakpoint", "watchpoint", etc.
- `enabled`: "y" or "n"
- `addr`: Memory address (e.g., "0x0000000000401234")
- `func`: Function name (if available)
- `file`: Source file name (if available)
- `fullname`: Full path to source file (if available)
- `line`: Line number (if available)
- `times`: Number of times this breakpoint has been hit (string)
- `original-location`: Original location string used to set the breakpoint

**Example output:**
```json
{
  "status": "success",
  "breakpoints": [
    {
      "number": "1",
      "type": "breakpoint",
      "enabled": "y",
      "addr": "0x0000000000016cd5",
      "func": "HeapColorStrategy::operator()",
      "file": "color_strategy.hpp",
      "fullname": "/home/user/project/src/color_strategy.hpp",
      "line": "119",
      "times": "3",
      "original-location": "color_strategy.hpp:119"
    }
  ],
  "count": 1
}
```

**Use this to:**
- Verify breakpoints were set at correct locations
- Check which breakpoints have been hit (times > 0)
- Find breakpoint numbers for deletion
- Confirm file paths resolved correctly

#### `gdb_continue`
Continue execution until next breakpoint.

**IMPORTANT:** Only use when program is PAUSED (at a breakpoint). If program hasn't started, use `gdb_execute_command` with "run" instead.

#### `gdb_step`
Step into next instruction (enters functions).

**IMPORTANT:** Only works when program is PAUSED at a specific location.

#### `gdb_next`
Step over to next line (doesn't enter functions).

**IMPORTANT:** Only works when program is PAUSED at a specific location.

#### `gdb_interrupt`
Interrupt (pause) a running program.

**Use when:**
- Program is running and hasn't hit a breakpoint
- You want to pause execution to inspect state
- Program appears stuck and you want to see where it is
- Commands are timing out because program is running

**After interrupting:** You can use `gdb_get_backtrace`, `gdb_get_variables`, etc.

### Data Inspection

#### `gdb_evaluate_expression`
Evaluate a C/C++ expression in the current context.

**Parameters:**
- `expression`: Expression to evaluate

**Examples:**
- `"x"` - Get value of variable x
- `"*ptr"` - Dereference pointer
- `"array[5]"` - Access array element
- `"obj->field"` - Access struct field

#### `gdb_get_variables`
Get local variables for a stack frame.

**Parameters:**
- `thread_id` (optional): Thread ID
- `frame`: Frame number (0 is current, default: 0)

#### `gdb_get_registers`
Get CPU register values for the current frame.

## Usage Examples

### Example 1: Analyzing a Core Dump

**User**: "Load the core dump at /tmp/core.12345, set the sysroot to /opt/sysroot, and tell me how many threads there were when it crashed."

**AI Actions**:
1. Start session with init commands:
```json
{
  "init_commands": [
    "file /path/to/executable",
    "core-file /tmp/core.12345",
    "set sysroot /opt/sysroot"
  ]
}
```
2. Get threads: `gdb_get_threads`
3. Report: "There were 8 threads when the program crashed."

### Example 2: Conditional Breakpoint Investigation

**User**: "Set a breakpoint at process_data but only when the count variable is greater than 100, then continue execution."

**AI Actions**:
1. Set conditional breakpoint:
```json
{
  "location": "process_data",
  "condition": "count > 100"
}
```
2. Continue execution: `gdb_continue`
3. When hit, inspect state

**For more detailed usage examples and workflows, see [examples/USAGE_GUIDE.md](examples/USAGE_GUIDE.md) and [examples/README.md](examples/README.md).**

## Advanced Usage

### Custom GDB Initialization Scripts

Create a `.gdb` file with your setup commands:

```gdb
# setup.gdb
file /path/to/myprogram
core-file /path/to/core

# Set up symbol paths
set sysroot /opt/sysroot
set solib-search-path /opt/libs:/usr/local/lib

# Convenience settings
set print pretty on
set print array on
set pagination off
```

Then use it:
```json
{
  "init_commands": ["source setup.gdb"]
}
```

### Python Initialization Scripts

You can also use GDB's Python API:

```python
# init.py
import gdb
gdb.execute("file /path/to/program")
gdb.execute("core-file /path/to/core")
# Custom analysis
```

Use with:
```json
{
  "init_commands": ["source init.py"]
}
```

### Working with Running Processes

While this server primarily works with core dumps and executables, you can attach to running processes:

```json
{
  "init_commands": [
    "attach 12345"  // PID of running process
  ]
}
```

Note: This requires appropriate permissions (usually root or same user).

## Troubleshooting

### Common Issues

**GDB Not Found**
```bash
which gdb
gdb --version
```

**Timeout Errors / Commands Not Responding**

The program is likely still running! When a program is running, GDB is busy and won't respond to other commands.

**Solution:** Use `gdb_interrupt` to pause the running program, then other commands will work.

**Program States:**
- **Not started**: Use `gdb_execute_command` with "run" or "start"
- **Running**: Program is executing - use `gdb_interrupt` to pause it
- **Paused** (at breakpoint): Use `gdb_continue`, `gdb_step`, `gdb_next`, inspect variables
- **Finished**: Program has exited - restart with "run" if needed

**Missing Debug Symbols**

Always check the `warnings` field in `gdb_start_session` response! Compile your programs with the `-g` flag.

**For detailed troubleshooting, installation issues, and more solutions, see [INSTALL.md](INSTALL.md#troubleshooting).**

## How It Works

1. **GDB/MI Protocol**: The server communicates with GDB using the Machine Interface (MI) protocol, the same interface used by IDEs.

2. **pygdbmi Library**: We use the excellent `pygdbmi` library to handle the low-level protocol details and response parsing.

3. **MCP Integration**: The server exposes GDB functionality as MCP tools, allowing AI assistants to:
   - Understand the available debugging operations
   - Execute commands with proper parameters
   - Interpret structured responses

4. **Session Management**: A single GDB session is maintained per server instance, allowing stateful debugging across multiple tool calls.

## Comparison with IDE Debuggers

This server provides similar capabilities to IDE debuggers:

| Feature | VS Code | CLion | GDB MCP Server |
|---------|---------|-------|----------------|
| GDB/MI Protocol | ✓ | ✓ | ✓ |
| Thread Inspection | ✓ | ✓ | ✓ |
| Breakpoints | ✓ | ✓ | ✓ |
| Variable Inspection | ✓ | ✓ | ✓ |
| Core Dump Analysis | ✓ | ✓ | ✓ |
| AI-Driven Analysis | ✗ | ✗ | ✓ |

## Contributing

Contributions welcome! Areas for improvement:
- Additional GDB commands
- Better error handling
- Async event notifications
- Multi-session support
- Enhanced output formatting

## License

MIT

## References

- [GDB Machine Interface (MI)](https://sourceware.org/gdb/current/onlinedocs/gdb/GDB_002fMI.html)
- [pygdbmi Documentation](https://github.com/cs01/pygdbmi)
- [Model Context Protocol](https://modelcontextprotocol.io/)
