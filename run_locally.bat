@echo off
setlocal

IF NOT EXIST ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate

echo Installing dependencies...
pip install -r requirements.txt

echo Running application...
python main.py

echo.
echo Application finished. Press any key to exit.
pause >nul
