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

```bash
# Install pipx if needed
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install gdb-mcp-server
cd /path/to/gdb-mcp
pipx install .
```

**For alternative installation methods (virtual environment, manual setup), see [INSTALL.md](INSTALL.md).**

## Configuration

### Claude Desktop

Add this to your Claude Desktop configuration file:

**Location:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

**For other installation methods and MCP clients, see [INSTALL.md](INSTALL.md#step-5-configure-your-mcp-client).**

## Available Tools

The GDB MCP Server provides 13 tools for controlling GDB debugging sessions:

**Session Management:**
- `gdb_start_session` - Start a new GDB session with optional initialization
- `gdb_execute_command` - Execute any GDB command (CLI or MI)
- `gdb_get_status` - Get current session status
- `gdb_stop_session` - Stop the current session

**Thread Inspection:**
- `gdb_get_threads` - List all threads
- `gdb_get_backtrace` - Get stack trace for a thread

**Breakpoints & Execution:**
- `gdb_set_breakpoint` - Set breakpoints with optional conditions
- `gdb_list_breakpoints` - List all breakpoints with structured data
- `gdb_continue` - Continue execution
- `gdb_step` - Step into functions
- `gdb_next` - Step over functions
- `gdb_interrupt` - Pause a running program

**Data Inspection:**
- `gdb_evaluate_expression` - Evaluate expressions
- `gdb_get_variables` - Get local variables
- `gdb_get_registers` - Get CPU registers

**For detailed documentation of each tool including parameters, return values, and examples, see [TOOLS.md](TOOLS.md).**

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

## Contributing

Contributions welcome! Areas for improvement:
- Additional GDB commands
- Better error handling
- Async event notifications
- Enhanced output formatting

## License

MIT

## References

- [GDB Machine Interface (MI)](https://sourceware.org/gdb/current/onlinedocs/gdb/GDB_002fMI.html)
- [pygdbmi Documentation](https://github.com/cs01/pygdbmi)
- [Model Context Protocol](https://modelcontextprotocol.io/)
