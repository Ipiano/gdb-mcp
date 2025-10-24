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
- `pipx` (recommended) - [Installation instructions](https://pipx.pypa.io/stable/installation/)

### Option 1: Using pipx (Recommended)

`pipx` installs the package in an isolated environment and makes the command globally available. This is the simplest and cleanest approach.

**For regular users:**
```bash
# Install from the repository directory
cd /path/to/gdb-mcp
pipx install .

# Or install directly from git (future)
# pipx install git+https://github.com/yourusername/gdb-mcp.git
```

**For developers (editable mode):**
```bash
# Install in editable mode for development
cd /path/to/gdb-mcp
pipx install -e .
```

**Installing pipx** (if not already installed):
```bash
# Linux/macOS
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Windows
py -m pip install --user pipx
py -m pipx ensurepath

# Or via package managers
# Ubuntu/Debian: sudo apt install pipx
# macOS: brew install pipx
# Fedora: sudo dnf install pipx
```

### Option 2: Automated Setup with Virtual Environment

If you prefer manual venv management or can't use pipx:

**Linux/macOS:**
```bash
cd /path/to/gdb-mcp
./setup-venv.sh
```

**Windows:**
```cmd
cd \path\to\gdb-mcp
setup-venv.bat
```

The script will create a virtual environment and install all dependencies.

### Option 3: Manual Virtual Environment Setup

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows

# Install package in editable mode
pip install -e .
```

### Option 4: Global pip Installation (Not Recommended)

```bash
# From the project directory
pip install .
```

Note: Global installation may conflict with other Python packages. Use pipx or virtual environments instead.

## Configuration

### Claude Desktop

Add this to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux**: `~/.config/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

#### Using pipx (Recommended - Simplest Configuration)

If you installed via `pipx`, use this simple configuration:

```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server",
      "args": [],
      "type": "stdio"
    }
  }
}
```

Or even simpler (args and type are optional):

```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

That's it! No paths to worry about - `pipx` makes `gdb-mcp-server` available globally.

#### Using Virtual Environment

If you used the venv setup scripts, point to the Python executable in your virtual environment:

**Linux/macOS:**
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

**Windows:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "C:\\absolute\\path\\to\\gdb-mcp\\venv\\Scripts\\python.exe",
      "args": ["-m", "gdb_mcp"]
    }
  }
}
```

### Other MCP Clients

The server uses stdio for communication and can be used with any MCP-compatible client.

**If installed with pipx:**
```bash
gdb-mcp-server
```

**If using virtual environment:**
```bash
# From project directory
./venv/bin/python -m gdb_mcp  # Linux/macOS
# or
venv\Scripts\python.exe -m gdb_mcp  # Windows
```

## Available Tools

### Session Management

#### `gdb_start_session`
Start a new GDB debugging session.

**Parameters:**
- `program` (optional): Path to executable to debug
- `args` (optional): Command-line arguments for the program
- `init_commands` (optional): List of GDB commands to run on startup

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
Execute any GDB command directly.

**Parameters:**
- `command`: GDB command to execute
- `timeout_sec`: Timeout in seconds (default: 5)

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

### Example 2: Finding Blocked Threads

**User**: "Find all threads that are blocked waiting for a mutex."

**AI Actions**:
1. Get all threads: `gdb_get_threads`
2. For each thread:
   - Get backtrace: `gdb_get_backtrace(thread_id=N)`
   - Check if backtrace contains mutex/lock functions
3. Report threads with mutex calls in their stack

### Example 3: Using a GDB Initialization Script

**User**: "I have a GDB script at setup.gdb that configures everything. Use it to start a session, then find the main thread."

**AI Actions**:
1. Start session:
```json
{
  "init_commands": ["source setup.gdb"]
}
```
2. Get threads and identify main thread
3. Get backtrace for main thread

### Example 4: Conditional Breakpoint Investigation

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

### Example 5: Analyzing a Running Program (Post-Mortem)

**User**: "The program is in core.dump. I think thread 3 was doing something wrong. Show me its backtrace and all local variables in the top frame."

**AI Actions**:
1. Start session with core dump
2. Get backtrace for thread 3: `gdb_get_backtrace(thread_id=3)`
3. Get variables in top frame: `gdb_get_variables(thread_id=3, frame=0)`
4. Present analysis

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

### GDB Not Found
Ensure GDB is installed and in your PATH:
```bash
which gdb
gdb --version
```

### Permission Errors
When attaching to processes, you may need:
```bash
# Linux: Allow ptrace for non-root
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

### Timeout Errors / Commands Not Responding

**Problem:** Commands time out with "Did not get response from gdb after X seconds"

**Common Cause:** The program is still running! When a program is running (hasn't hit a breakpoint, hasn't finished), GDB is busy and won't respond to other commands.

**Solution:**
1. Use `gdb_interrupt` to pause the running program
2. After interrupting, other commands will work again
3. Check if breakpoints were actually hit (they won't trigger if program exits before reaching them)

**Understanding Program States:**
- **Not started**: Use `gdb_execute_command` with "run" or "start"
- **Running**: Program is executing - use `gdb_interrupt` to pause it
- **Paused** (at breakpoint): Use `gdb_continue`, `gdb_step`, `gdb_next`, inspect variables
- **Finished**: Program has exited - restart with "run" if needed

**For genuinely slow operations,** increase the timeout:
```json
{
  "command": "...",
  "timeout_sec": 30
}
```

### Symbol Loading Issues
Ensure debug symbols are available and paths are correct:
```json
{
  "init_commands": [
    "set sysroot /correct/path",
    "set solib-search-path /path/to/libs",
    "set debug-file-directory /usr/lib/debug"
  ]
}
```

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
