@echo off
REM Setup script for GDB MCP Server virtual environment (Windows)

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%venv

echo Setting up GDB MCP Server virtual environment...

REM Check if Python 3 is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.10 or higher.
    exit /b 1
)

echo Found Python:
python --version

REM Check if virtual environment exists
if exist "%VENV_DIR%" (
    echo Virtual environment already exists at %VENV_DIR%
    set /p RECREATE="Do you want to recreate it? (y/N): "
    if /i "!RECREATE!"=="y" (
        echo Removing existing virtual environment...
        rmdir /s /q "%VENV_DIR%"
    ) else (
        echo Keeping existing virtual environment.
        echo To activate it, run: venv\Scripts\activate
        exit /b 0
    )
)

echo Creating virtual environment...
python -m venv "%VENV_DIR%"

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies...
pip install -r requirements.txt

echo Installing gdb-mcp-server in editable mode...
pip install -e .

echo.
echo Setup complete!
echo.
echo Virtual environment created at: %VENV_DIR%
echo Python executable: %VENV_DIR%\Scripts\python.exe
echo.
echo To activate the virtual environment manually, run:
echo   venv\Scripts\activate
echo.
echo To configure Claude Desktop, use this configuration:
echo.
echo {
echo   "mcpServers": {
echo     "gdb": {
echo       "command": "%VENV_DIR%\Scripts\python.exe",
echo       "args": ["-m", "gdb_mcp"]
echo     }
echo   }
echo }
echo.

endlocal
