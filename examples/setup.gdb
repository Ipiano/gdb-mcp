# Example GDB initialization script
# This demonstrates how to set up a debugging session

# Load the executable
file sample_program

# If you have a core dump, uncomment this:
# core-file core.12345

# Symbol path configuration (adjust as needed)
# set sysroot /path/to/sysroot
# set solib-search-path /path/to/libs

# Convenience settings for better output
set print pretty on
set print array on
set print array-indexes on
set pagination off

# Thread settings
set print thread-events on

# Show what we loaded
info files
info threads

# Common breakpoints for this example program
# Uncomment these if you want to set breakpoints automatically:
# break main
# break worker_thread
# break mutex_user_thread
# break calculate_sum

# Display some useful information
echo \n=== GDB Session Ready ===\n
echo Program loaded: sample_program\n
echo Use 'run' to start execution\n
echo Or use MCP tools to control the session\n
