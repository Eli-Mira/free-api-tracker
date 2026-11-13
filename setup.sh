#!/bin/bash
set -e
echo "=== Installing free-api-tracker ==="
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "Done. Run: python main.py"
