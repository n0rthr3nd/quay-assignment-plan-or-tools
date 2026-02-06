$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

Write-Host "Activating virtual environment..."
& ".\.venv\Scripts\Activate.ps1"

Write-Host "Installing dependencies..."
pip install -r requirements.txt

Write-Host "Running application..."
python main.py

Write-Host "`nApplication finished. Press Enter to exit."
Read-Host
