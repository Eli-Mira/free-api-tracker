@echo off
echo === Installing free-api-tracker ===
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
echo Done. Run: python main.py
