# GDB MCP Server Tests

This directory contains unit and integration tests for the GDB MCP Server.

## Running Tests

### Install Development Dependencies

```bash
# Install the package with dev dependencies
pip install -e ".[dev]"
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=gdb_mcp --cov-report=html
```

### Run Specific Tests

```bash
# Run only unit tests (excluding integration tests)
pytest -m "not integration"

# Run only a specific test file
pytest tests/test_gdb_interface.py

# Run only a specific test
pytest tests/test_gdb_interface.py::TestGDBSession::test_session_initialization
```

## Test Structure

- `test_gdb_interface.py` - Unit tests for the GDB interface layer
- `test_server.py` - Unit tests for the MCP server and argument models

## Test Categories

Tests are marked with pytest markers:

- `@pytest.mark.integration` - Tests that require GDB to be installed
- `@pytest.mark.slow` - Tests that take significant time to run

## Writing New Tests

When adding new tests:

1. Follow the existing naming conventions (`test_*.py`, `Test*`, `test_*`)
2. Use descriptive test names that explain what is being tested
3. Mock external dependencies (GdbController) when possible
4. Mark integration tests appropriately

## Continuous Integration

Tests run automatically on GitHub Actions for:
- Python 3.10, 3.11, and 3.12
- Every push to main/master
- Every pull request

See `.github/workflows/test.yml` for the CI configuration.
