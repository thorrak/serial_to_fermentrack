#!/bin/bash

# Activate the virtual environment
source venv/bin/activate

# Clean up previous coverage data
coverage erase

# Run pytest with coverage
python -m pytest --cov=. --cov-config=.coveragerc

# Generate HTML report
coverage html

echo "Coverage report generated in the htmlcov directory"
echo "Open htmlcov/index.html in your browser to view the report"