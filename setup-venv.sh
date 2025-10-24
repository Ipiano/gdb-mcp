#!/bin/bash
# Setup script for GDB MCP Server virtual environment

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"

echo "Setting up GDB MCP Server virtual environment..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.10 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Found Python $PYTHON_VERSION"

# Create virtual environment
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at $VENV_DIR"
    read -p "Do you want to recreate it? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing virtual environment..."
        rm -rf "$VENV_DIR"
    else
        echo "Keeping existing virtual environment."
        echo "To activate it, run: source venv/bin/activate"
        exit 0
    fi
fi

echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Installing gdb-mcp-server in editable mode..."
pip install -e .

echo ""
echo "✓ Setup complete!"
echo ""
echo "Virtual environment created at: $VENV_DIR"
echo "Python executable: $VENV_DIR/bin/python"
echo ""
echo "To activate the virtual environment manually, run:"
echo "  source venv/bin/activate"
echo ""
echo "To configure Claude Desktop, use this configuration:"
echo ""
echo '{
  "mcpServers": {
    "gdb": {
      "command": "'$VENV_DIR'/bin/python",
      "args": ["-m", "gdb_mcp"]
    }
  }
}'
echo ""
