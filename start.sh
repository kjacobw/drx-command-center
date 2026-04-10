#!/bin/bash
# DRX Command Center startup script
# Handles venv creation + dependency install on first run

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt -q

echo "Starting DRX Command Center..."
uvicorn main:app --host 0.0.0.0 --port 8080
