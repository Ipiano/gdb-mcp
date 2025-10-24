# Quick Installation Guide

## TL;DR - Fast Setup

### Recommended: Using pipx (Simplest)

**1. Install pipx if not already installed:**
```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

**2. Install gdb-mcp-server:**
```bash
cd /path/to/gdb-mcp
pipx install .
# For developers: pipx install -e .
```

**3. Add to Claude Desktop config:**
```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

**4. Restart Claude Desktop**

That's it! No paths, no virtual environment management needed.

---

### Alternative: Using Virtual Environment

**1. Run the setup script:**
```bash
./setup-venv.sh  # Linux/macOS
# or
setup-venv.bat   # Windows
```

**2. Copy the configuration it outputs to your Claude Desktop config**

**3. Restart Claude Desktop**

---

## Detailed Instructions

## Method 1: pipx Installation (Recommended)

### Step 1: Install pipx

If you don't have pipx installed:

**Linux/macOS:**
```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
# Restart your terminal or run: source ~/.bashrc (or ~/.zshrc)
```

**Windows:**
```cmd
py -m pip install --user pipx
py -m pipx ensurepath
# Restart your terminal
```

**Or use package managers:**
```bash
# Ubuntu/Debian
sudo apt install pipx

# macOS
brew install pipx

# Fedora
sudo dnf install pipx
```

### Step 2: Clone/Download the Project

```bash
cd /path/to/your/projects
git clone <repository-url> gdb-mcp
cd gdb-mcp
```

### Step 3: Install with pipx

**For regular users:**
```bash
pipx install .
```

**For developers (editable mode):**
```bash
pipx install -e .
```

This installs the `gdb-mcp-server` command globally, isolated from other Python packages.

**Important:** Wait for `pipx install` to fully complete before proceeding. You'll see output like "installed package gdb-mcp-server" or "done" when finished.

### Step 4: Verify Installation

```bash
# Test the command works
which gdb-mcp-server  # Linux/macOS
# or
where gdb-mcp-server  # Windows

# Test the server starts
gdb-mcp-server  # Press Ctrl+C to stop
```

You should see: `INFO:gdb_mcp.server:GDB MCP Server starting...`

**Troubleshooting:** If you get `ModuleNotFoundError: No module named 'mcp.types'` or similar import errors, the installation may not have fully completed. Wait a moment and try again, or run:
```bash
pipx reinstall gdb-mcp-server
```

### Step 5: Configure Your MCP Client

1. Find your Claude Desktop config file location:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Edit the file (create if it doesn't exist)

3. Add this simple configuration:

```json
{
  "mcpServers": {
    "gdb": {
      "command": "gdb-mcp-server"
    }
  }
}
```

Or with explicit type (optional):

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

That's it! No paths needed - pipx makes the command globally available.

### Step 6: Restart Claude Desktop and Test

1. Close and reopen Claude Desktop
2. Try asking: "Do you have access to GDB debugging tools?"
3. Claude should confirm it has access to the `gdb_*` tools

---

## Method 2: Virtual Environment Installation

### Step 1: Clone/Download the Project

```bash
cd /path/to/your/projects
git clone <repository-url> gdb-mcp
cd gdb-mcp
```

### Step 2: Run Setup Script

**Linux/macOS:**
```bash
chmod +x setup-venv.sh
./setup-venv.sh
```

**Windows (Command Prompt):**
```cmd
setup-venv.bat
```

The script will create a virtual environment and install all dependencies.

### Step 2.5: Verify Installation (Optional but Recommended)

Before configuring Claude Desktop, verify the installation works:

**Test the module can be imported:**
```bash
# From any directory
/absolute/path/to/gdb-mcp/venv/bin/python -c "import gdb_mcp; print('OK')"
```

**Test the server can start:**
```bash
# From any directory (Ctrl+C to stop)
/absolute/path/to/gdb-mcp/venv/bin/python -m gdb_mcp
```

You should see: `INFO:gdb_mcp.server:GDB MCP Server starting...`

This confirms:
- ✓ The virtual environment is set up correctly
- ✓ All dependencies are installed
- ✓ The module can be found from any working directory
- ✓ The server can start successfully

If you see errors, check the Troubleshooting section below.

### Step 3: Configure Your MCP Client

1. Find your Claude Desktop config file location:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Edit the file (create if it doesn't exist)

3. Add the GDB MCP server configuration with absolute paths:

**Example for macOS/Linux** (adjust path to match your installation):
```json
{
  "mcpServers": {
    "gdb": {
      "command": "/Users/yourname/projects/gdb-mcp/venv/bin/python",
      "args": ["-m", "gdb_mcp"]
    }
  }
}
```

**Example for Windows** (adjust path to match your installation):
```json
{
  "mcpServers": {
    "gdb": {
      "command": "C:\\Users\\yourname\\projects\\gdb-mcp\\venv\\Scripts\\python.exe",
      "args": ["-m", "gdb_mcp"]
    }
  }
}
```

**Pro tip:** The setup script displays the exact configuration for your system. Just copy and paste!

### Step 4: Restart Claude Desktop

Close and reopen Claude Desktop to load the new MCP server.

### Step 5: Verify It Works

In Claude Desktop, try:
```
Do you have access to GDB debugging tools?
```

Claude should confirm it has access to the `gdb_*` tools.

---

## Finding Your Absolute Path

If you're not sure of the absolute path to your gdb-mcp directory:

**Linux/macOS:**
```bash
cd /path/to/gdb-mcp
pwd
# This shows the full path, e.g., /home/username/projects/gdb-mcp
```

Your Python path would be: `/home/username/projects/gdb-mcp/venv/bin/python`

**Windows:**
```cmd
cd \path\to\gdb-mcp
cd
# This shows the full path, e.g., C:\Users\username\projects\gdb-mcp
```

Your Python path would be: `C:\Users\username\projects\gdb-mcp\venv\Scripts\python.exe`

---

## Example Configurations

### Multiple MCP Servers

If you already have other MCP servers configured:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/yourname/Desktop"]
    },
    "gdb": {
      "command": "/Users/yourname/projects/gdb-mcp/venv/bin/python",
      "args": ["-m", "gdb_mcp"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "your-token"
      }
    }
  }
}
```

### With Environment Variables

If you need to set environment variables for GDB:

```json
{
  "mcpServers": {
    "gdb": {
      "command": "/absolute/path/to/gdb-mcp/venv/bin/python",
      "args": ["-m", "gdb_mcp"],
      "env": {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "GDB_CUSTOM_VAR": "value"
      }
    }
  }
}
```

---

## Troubleshooting

### "Command not found" or "File not found"

**Problem:** Claude Desktop can't find the Python executable.

**Solution:**
1. Make sure you're using an **absolute path** (starts with `/` on Linux/macOS or `C:\` on Windows)
2. Verify the file exists:
   ```bash
   ls /path/to/gdb-mcp/venv/bin/python  # Linux/macOS
   dir C:\path\to\gdb-mcp\venv\Scripts\python.exe  # Windows
   ```

### "Module not found: gdb_mcp"

**Problem:** The package isn't installed in the virtual environment.

**Solution:** Re-run the setup script or manually install:
```bash
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

pip install -e .
```

### "GDB not found"

**Problem:** GDB isn't installed or not in PATH.

**Solution:** Install GDB:
```bash
# Debian/Ubuntu
sudo apt install gdb

# macOS
brew install gdb

# Fedora/RHEL
sudo dnf install gdb
```

### Virtual Environment Not Created

**Problem:** `python3 -m venv` fails.

**Solution:** Install venv package:
```bash
# Debian/Ubuntu
sudo apt install python3-venv

# Or use virtualenv instead
pip install virtualenv
virtualenv venv
```

### Claude Desktop Doesn't Show GDB Tools

**Problem:** MCP server isn't loading.

**Solutions:**
1. Check Claude Desktop logs (usually in the app's help/debug menu)
2. Verify the JSON configuration is valid (no syntax errors)
3. Make sure the path uses forward slashes `/` or escaped backslashes `\\` (not single `\`)
4. Restart Claude Desktop after making config changes

---

## Manual Testing

You can test the server manually before configuring Claude Desktop.

**Method 1: Direct path (recommended - same as Claude Desktop uses):**
```bash
# From any directory, using absolute path to venv Python
/absolute/path/to/gdb-mcp/venv/bin/python -m gdb_mcp  # Linux/macOS
# or
C:\absolute\path\to\gdb-mcp\venv\Scripts\python.exe -m gdb_mcp  # Windows

# You should see: INFO:gdb_mcp.server:GDB MCP Server starting...
# Press Ctrl+C to exit
```

**Method 2: After activating the virtual environment:**
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Run the server
python -m gdb_mcp

# It should start and wait for input (Ctrl+C to exit)
```

**Important:** Method 1 (direct path) is preferred because it's exactly how Claude Desktop will run it. If Method 1 works from any directory, then Claude Desktop will work too.

---

## Updating the Server

To update to a newer version:

```bash
cd /path/to/gdb-mcp
git pull
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install -e .
```

Then restart Claude Desktop.

---

## Uninstalling

1. Remove the gdb-mcp directory:
   ```bash
   rm -rf /path/to/gdb-mcp  # Linux/macOS
   # or
   rmdir /s /q C:\path\to\gdb-mcp  # Windows
   ```

2. Remove the configuration from Claude Desktop config file

3. Restart Claude Desktop

---

## Getting Help

If you encounter issues:

1. Check the [README.md](README.md) for detailed documentation
2. Verify GDB is installed: `gdb --version`
3. Check Python version: `python3 --version` (should be 3.10+)
4. Look at Claude Desktop logs for error messages
5. Try running the server manually (see "Manual Testing" above)
