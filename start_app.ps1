if (-not (Test-Path ".venv")) {
    Write-Host "Virtual environment not found! Please run 'python -m venv .venv' first." -ForegroundColor Red
    exit
}

& ".\.venv\Scripts\Activate.ps1"
Write-Host "Starting BAP+QCAP Web Application..." -ForegroundColor Cyan
python app.py
