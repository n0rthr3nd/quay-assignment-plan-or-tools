@echo off
if not exist ".venv" (
    echo Virtual environment not found! Please run 'python -m venv .venv' first.
    pause
    exit /b
)

call .venv\Scripts\activate
echo Starting BAP+QCAP Web Application...
python app.py
pause
