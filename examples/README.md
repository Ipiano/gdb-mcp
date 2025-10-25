# GDB MCP Server Examples

This directory contains example programs and scripts to help you test and understand the GDB MCP Server.

**For detailed step-by-step workflows and usage patterns, see [USAGE_GUIDE.md](USAGE_GUIDE.md).**

## Files

- `sample_program.c` - A multi-threaded C program with various debugging scenarios
- `Makefile` - Build script for the sample program
- `setup.gdb` - Example GDB initialization script
- `USAGE_GUIDE.md` - Step-by-step guide for using the MCP server

## Quick Start

### 1. Build the Sample Program

```bash
cd examples
make
```

This creates a `sample_program` executable with debug symbols.

### 2. Test Scenarios

The sample program includes several debugging scenarios:

- **Multiple threads**: 4 threads running concurrently
- **Mutex operations**: Threads using mutex locks
- **Shared counter**: Multiple threads incrementing a counter
- **Array operations**: Thread modifying array elements
- **Function calls**: Multiple stack frames to inspect

### 3. Running with the MCP Server

Once you have the GDB MCP server configured in Claude Desktop (or another MCP client), you can:

**Scenario A: Load executable and run**
```
"Start a GDB session with examples/sample_program"
"Set a breakpoint at main and run the program"
"Tell me about all the threads"
```

**Scenario B: Use the initialization script**
```
"Start a GDB session using the script examples/setup.gdb"
"Run the program and break when it reaches worker_thread"
"Show me the variables in the current frame"
```

**Scenario C: Analyze without running**
```
"Start a GDB session with examples/sample_program"
"Show me all the functions in the program"
"What are the parameters of the worker_thread function?"
```

## Example AI Prompts

Here are some prompts you can use with an AI that has access to the GDB MCP server:

### Thread Analysis
```
"Load examples/sample_program and tell me:
 1. How many threads does it create?
 2. What functions do the threads execute?
 3. What mutexes are being used?"
```

### Breakpoint and Inspection
```
"Debug examples/sample_program:
 1. Set a breakpoint at calculate_sum
 2. Run the program
 3. When it hits the breakpoint, show me the values of 'arr' and 'size'
 4. Calculate what the sum should be"
```

### Step-by-Step Execution
```
"Debug examples/sample_program:
 1. Break at main
 2. Run to the breakpoint
 3. Step through the next 10 lines
 4. Tell me what the counter value is"
```

### Thread State Analysis
```
"After starting examples/sample_program:
 1. Let it run for a bit then interrupt it
 2. Show me what each thread is doing
 3. Which threads are waiting on mutexes?"
```

## Creating a Core Dump for Testing

If you want to test core dump analysis:

```bash
# Enable core dumps
ulimit -c unlimited

# Run the program (you may need to modify it to crash)
./sample_program

# Or send it a signal
./sample_program &
PID=$!
sleep 1
kill -SEGV $PID

# This creates a core file (usually core.PID or just core)
ls -lh core*
```

Then use it with the MCP server:
```
"Load the executable examples/sample_program and core dump examples/core.12345
 Tell me:
 1. How many threads were running?
 2. What was each thread doing when it crashed?
 3. What are the values of the global variables?"
```

## Manual GDB Testing

You can also test the setup script manually with GDB:

```bash
# Using the init script
gdb -x setup.gdb

# Or step by step
gdb sample_program
(gdb) source setup.gdb
(gdb) break main
(gdb) run
(gdb) info threads
(gdb) backtrace
```

For a complete reference of all available tools with detailed documentation, see [TOOLS.md](../TOOLS.md).

## Troubleshooting

**Program won't compile:**
- Ensure you have gcc installed: `gcc --version`
- Install build tools: `sudo apt install build-essential` (Debian/Ubuntu)

**No debug symbols:**
- Make sure you compile with `-g` flag (the Makefile includes this)
- Check with: `file sample_program` (should say "not stripped")

**Thread issues:**
- Ensure pthread library is available
- Link with `-pthread` flag (included in Makefile)

**GDB not found:**
- Install GDB: `sudo apt install gdb` (Debian/Ubuntu)
- Or: `brew install gdb` (macOS)
