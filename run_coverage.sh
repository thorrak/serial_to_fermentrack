#!/bin/bash

# Synchronize the virtual environment
uv sync

# Clean up previous coverage data
uv run coverage erase

# Run pytest with coverage
uv run pytest --cov=. --cov-config=.coveragerc

# Generate HTML report
uv run coverage html

echo "Coverage report generated in the htmlcov directory"
echo "Open htmlcov/index.html in your browser to view the report"