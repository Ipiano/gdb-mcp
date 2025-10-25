# GDB MCP Server - Tools Reference

This document provides detailed documentation for all available tools in the GDB MCP Server.

## Session Management

### `gdb_start_session`
Start a new GDB debugging session.

**Parameters:**
- `program` (optional): Path to executable to debug
- `args` (optional): Command-line arguments for the program
- `init_commands` (optional): List of GDB commands to run on startup
- `env` (optional): Environment variables to set for the debugged program (dictionary of name-value pairs)
- `gdb_path` (optional): Path to GDB executable (default: "gdb")

**Returns:**
- `status`: "success" or "error"
- `message`: Status message
- `program`: Program path
- `startup_output` (optional): GDB's initial output when loading the program
- `warnings` (optional): Array of critical warnings detected, such as:
  - "No debugging symbols found - program was not compiled with -g"
  - "File is not an executable"
  - "Program file not found"
- `env_output` (optional): Output from setting environment variables if env was provided
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

**Example with custom GDB path:**
```json
{
  "program": "/path/to/myprogram",
  "gdb_path": "/usr/local/bin/gdb-custom"
}
```

Use `gdb_path` when you need to use a specific GDB version or when GDB is not in your PATH.

**Example with environment variables:**
```json
{
  "program": "/path/to/myprogram",
  "env": {
    "LD_LIBRARY_PATH": "/custom/libs:/opt/libs",
    "DEBUG_MODE": "1",
    "LOG_LEVEL": "verbose"
  }
}
```

Environment variables are set for the debugged program before execution. This is useful for:
- Setting library search paths (LD_LIBRARY_PATH, DYLD_LIBRARY_PATH)
- Configuring application behavior (DEBUG_MODE, LOG_LEVEL, etc.)
- Testing with different environment configurations

### `gdb_execute_command`
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

### `gdb_get_status`
Get the current status of the GDB session.

### `gdb_stop_session`
Stop the current GDB session.

## Thread Inspection

### `gdb_get_threads`
Get information about all threads in the debugged process.

**Returns:**
- List of threads with IDs and states
- Current thread ID
- Thread count

### `gdb_get_backtrace`
Get stack backtrace for a thread.

**Parameters:**
- `thread_id` (optional): Thread ID (None for current thread)
- `max_frames`: Maximum frames to retrieve (default: 100)

## Breakpoints and Execution Control

### `gdb_set_breakpoint`
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

### `gdb_list_breakpoints`
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

### `gdb_continue`
Continue execution until next breakpoint.

**IMPORTANT:** Only use when program is PAUSED (at a breakpoint). If program hasn't started, use `gdb_execute_command` with "run" instead.

### `gdb_step`
Step into next instruction (enters functions).

**IMPORTANT:** Only works when program is PAUSED at a specific location.

### `gdb_next`
Step over to next line (doesn't enter functions).

**IMPORTANT:** Only works when program is PAUSED at a specific location.

### `gdb_interrupt`
Interrupt (pause) a running program.

**Use when:**
- Program is running and hasn't hit a breakpoint
- You want to pause execution to inspect state
- Program appears stuck and you want to see where it is
- Commands are timing out because program is running

**After interrupting:** You can use `gdb_get_backtrace`, `gdb_get_variables`, etc.

## Data Inspection

### `gdb_evaluate_expression`
Evaluate a C/C++ expression in the current context.

**Parameters:**
- `expression`: Expression to evaluate

**Examples:**
- `"x"` - Get value of variable x
- `"*ptr"` - Dereference pointer
- `"array[5]"` - Access array element
- `"obj->field"` - Access struct field

### `gdb_get_variables`
Get local variables for a stack frame.

**Parameters:**
- `thread_id` (optional): Thread ID
- `frame`: Frame number (0 is current, default: 0)

### `gdb_get_registers`
Get CPU register values for the current frame.
