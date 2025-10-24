# GDB MCP Server Usage Guide

This guide provides step-by-step examples of using the GDB MCP Server with an AI assistant.

## Prerequisites

1. GDB MCP Server installed and configured in your MCP client
2. Sample program built (`cd examples && make`)
3. AI assistant with access to the GDB MCP tools

## Example Workflow 1: Basic Debugging Session

### Goal
Load a program, run it with a breakpoint, and inspect variables.

### Step-by-Step

**Step 1: Start the session**

User prompt:
```
Start a GDB session with the program at examples/sample_program
```

AI will use: `gdb_start_session` with `program="examples/sample_program"`

**Step 2: Set a breakpoint**

User prompt:
```
Set a breakpoint at the main function
```

AI will use: `gdb_set_breakpoint` with `location="main"`

**Step 3: Run the program**

User prompt:
```
Run the program
```

AI will use: `gdb_execute_command` with `command="run"`

**Step 4: Inspect variables**

User prompt:
```
Show me all the local variables
```

AI will use: `gdb_get_variables` with default parameters

**Step 5: Continue execution**

User prompt:
```
Continue until the next breakpoint or completion
```

AI will use: `gdb_continue`

## Example Workflow 2: Thread Analysis

### Goal
Analyze thread behavior in a multi-threaded program.

### Step-by-Step

**Step 1: Start with initialization**

User prompt:
```
Start a GDB session with examples/sample_program, then run the program
with a breakpoint at worker_thread
```

AI actions:
1. `gdb_start_session` with `program="examples/sample_program"`
2. `gdb_set_breakpoint` with `location="worker_thread"`
3. `gdb_execute_command` with `command="run"`

**Step 2: Analyze threads**

User prompt:
```
How many threads are there and what is each one doing?
```

AI actions:
1. `gdb_get_threads` to get thread list
2. For each thread: `gdb_get_backtrace(thread_id=N)` to see what it's doing
3. Summarize findings

**Step 3: Inspect specific thread**

User prompt:
```
Show me the local variables for thread 2
```

AI actions:
1. `gdb_get_backtrace(thread_id=2)` to see the stack
2. `gdb_get_variables(thread_id=2, frame=0)` to get variables

**Step 4: Evaluate expression**

User prompt:
```
What's the value of counter + 10 in the current context?
```

AI will use: `gdb_evaluate_expression` with `expression="counter + 10"`

## Example Workflow 3: Core Dump Analysis

### Goal
Analyze a crashed program from a core dump.

### Setup
First, create a core dump (you might need to modify the program to crash):
```bash
ulimit -c unlimited
./examples/sample_program &
PID=$!
sleep 1
kill -ABRT $PID  # Force a crash
```

### Step-by-Step

**Step 1: Load core dump**

User prompt:
```
Load the executable examples/sample_program and the core dump at core.12345
```

AI will use: `gdb_start_session` with:
```json
{
  "init_commands": [
    "file examples/sample_program",
    "core-file core.12345"
  ]
}
```

**Step 2: Investigate crash**

User prompt:
```
Tell me everything about how this program crashed:
- How many threads were there?
- What was each thread doing?
- What were the values of global variables?
```

AI actions:
1. `gdb_get_threads` - Get thread count and IDs
2. For each thread: `gdb_get_backtrace(thread_id=N)` - See call stacks
3. `gdb_evaluate_expression` for each global variable (counter, array)
4. Compile comprehensive crash report

**Step 3: Detailed frame analysis**

User prompt:
```
For the thread that crashed (or thread 1), show me all variables
in the top 3 stack frames
```

AI actions:
1. `gdb_get_variables(thread_id=1, frame=0)`
2. `gdb_get_variables(thread_id=1, frame=1)`
3. `gdb_get_variables(thread_id=1, frame=2)`
4. Present organized results

## Example Workflow 4: Using Initialization Scripts

### Goal
Use a pre-configured GDB script for complex setup.

### Step-by-Step

**Step 1: Start with script**

User prompt:
```
Start a debugging session using the initialization script at examples/setup.gdb
```

AI will use: `gdb_start_session` with:
```json
{
  "init_commands": ["source examples/setup.gdb"]
}
```

**Step 2: Verify setup**

User prompt:
```
What program is loaded and what are the current breakpoints?
```

AI actions:
1. `gdb_execute_command` with `command="info files"` to see loaded program
2. `gdb_execute_command` with `command="info breakpoints"` to list breakpoints

**Step 3: Work with the session**

Now you can continue debugging normally - the session is pre-configured.

## Example Workflow 5: Conditional Breakpoints

### Goal
Find when a specific condition occurs.

### Step-by-Step

**Step 1: Set conditional breakpoint**

User prompt:
```
Start debugging examples/sample_program. Set a breakpoint at worker_thread
but only when the counter variable is greater than 5
```

AI actions:
1. `gdb_start_session` with `program="examples/sample_program"`
2. `gdb_set_breakpoint` with:
   ```json
   {
     "location": "worker_thread",
     "condition": "counter > 5"
   }
   ```

**Step 2: Run and inspect**

User prompt:
```
Run the program and when it hits the breakpoint, tell me:
- Which thread hit it?
- What's the value of counter?
- What are the local variables?
```

AI actions:
1. `gdb_execute_command` with `command="run"`
2. `gdb_get_threads` to find current thread
3. `gdb_evaluate_expression` with `expression="counter"`
4. `gdb_get_variables` to get locals

## Example Workflow 6: Finding Mutex Contentions

### Goal
Identify threads waiting on mutexes.

### Step-by-Step

**Step 1: Start and run**

User prompt:
```
Debug examples/sample_program. Let it run for a bit, then pause it and
tell me which threads are blocked on mutexes
```

AI actions:
1. `gdb_start_session` with `program="examples/sample_program"`
2. `gdb_execute_command` with `command="run &"` (background)
3. Wait a moment (or use timer)
4. `gdb_execute_command` with `command="interrupt"` to pause
5. `gdb_get_threads` to get all threads
6. For each thread: `gdb_get_backtrace(thread_id=N)`
7. Analyze backtraces for pthread_mutex_lock or similar functions

**Step 2: Detailed analysis**

User prompt:
```
For the threads waiting on mutexes, show me their full call stacks
```

AI will present the full backtraces for threads identified in step 1.

## Advanced Techniques

### Custom Symbol Paths

When debugging with relocated symbols or custom library paths:

```
Start a GDB session with these initialization commands:
1. Load examples/sample_program
2. Set sysroot to /opt/custom/sysroot
3. Add /opt/custom/libs to the library search path
```

AI will use: `gdb_start_session` with:
```json
{
  "init_commands": [
    "file examples/sample_program",
    "set sysroot /opt/custom/sysroot",
    "set solib-search-path /opt/custom/libs"
  ]
}
```

### Examining Memory

```
At the current point, examine the memory at address 0x12345678,
showing 64 bytes in hexadecimal
```

AI will use: `gdb_execute_command` with `command="x/64xb 0x12345678"`

### Assembly-Level Debugging

```
Show me the assembly code for the current function and the values
of all CPU registers
```

AI actions:
1. `gdb_execute_command` with `command="disassemble"`
2. `gdb_get_registers` to get register values

### Calling Functions

```
In the current context, call the calculate_sum function with
array and size 5, and tell me what it returns
```

AI will use: `gdb_evaluate_expression` with `expression="calculate_sum(array, 5)"`

## Common Patterns

### Pattern 1: "Find and Fix" Workflow
1. Start session with program
2. Run until error/crash
3. Get backtrace to understand context
4. Inspect variables to find bad values
5. Set breakpoint earlier in execution
6. Restart and debug from there

### Pattern 2: "Multi-Thread Investigation"
1. Start session and run program
2. Get all threads
3. For each thread: get backtrace
4. Identify interesting threads
5. Deep dive into specific threads with variable inspection

### Pattern 3: "Post-Mortem Analysis"
1. Load core dump
2. Get thread states
3. Examine crashed thread's stack
4. Look at global state
5. Reconstruct sequence of events

### Pattern 4: "Watch Point Debugging"
1. Set breakpoint at program start
2. Run to breakpoint
3. Set watchpoint on variable
4. Continue and catch when variable changes
5. Inspect who changed it and why

## Troubleshooting

### Session Not Starting
- Check that the program path is correct and absolute
- Verify GDB is installed: `which gdb`
- Check file permissions on the executable

### No Debug Symbols
- Recompile with `-g` flag
- Check with: `file examples/sample_program` (should say "not stripped")
- Use: `gdb_execute_command` with `command="info sources"` to verify

### Thread Information Missing
- Ensure program is compiled with `-pthread`
- Check if program is actually multi-threaded
- Use: `gdb_execute_command` with `command="info threads"` for raw output

### Timeout Errors
- Increase timeout for slow operations
- Use `timeout_sec` parameter in `gdb_execute_command`
- Some operations may need 10-30 seconds for large programs

## Tips for Working with AI

1. **Be Specific**: Instead of "debug this program", say "start a GDB session with this program and tell me about its threads"

2. **Sequential Steps**: Break complex tasks into steps: "First load the program, then set a breakpoint at main, then run it"

3. **Context Matters**: The AI maintains session state, so you can say "now inspect thread 3" after asking about threads

4. **Use Real Paths**: Always provide full or relative paths to executables and core dumps

5. **Leverage Init Scripts**: For complex setups, create a .gdb file and reference it

6. **Ask for Summaries**: "Summarize what you found" helps the AI organize information

## Next Steps

- Try the example prompts with your MCP client
- Create your own debugging scenarios
- Write custom GDB scripts for your projects
- Experiment with core dump analysis
- Practice conditional breakpoints and watchpoints
