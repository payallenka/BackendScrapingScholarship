#!/bin/bash
# Start the scholarship aggregator backend

set -e
cd "$(dirname "$0")"

# Create venv if needed
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# Install deps if needed
if ! venv/bin/python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing backend dependencies..."
  venv/bin/pip install -r backend/requirements.txt -q
fi

if ! venv/bin/python3 -c "import bs4" 2>/dev/null; then
  echo "Installing scraper dependencies..."
  venv/bin/pip install -r scrapers/requirements.txt -q
fi

echo ""
echo "Starting ScholarshipHub on http://localhost:8000"
echo "  → Frontend:  http://localhost:8000"
echo "  → API Docs:  http://localhost:8000/docs"
echo "  → Scrape:    POST http://localhost:8000/api/scrape"
echo ""

PYTHONPATH=. venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
