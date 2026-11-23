@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  AquaCount - hatchery launcher (Windows). Double-click to start.
REM  Runs fully offline after the first run. Dashboard: http://localhost:5000
REM  Other devices on the same Wi-Fi: use the "same Wi-Fi/LAN" address printed below.
REM ─────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating the Python environment. This needs internet once.
  py -3.11 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Could not create .venv - install Python 3.10 or 3.11 from python.org and try again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements-prod.txt
)

if not exist "models\best.onnx" (
  echo models\best.onnx is missing. Copy the model file into the models folder.
  pause
  exit /b 1
)

REM Open the dashboard once the server has had a few seconds to load the model.
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:5000"

".venv\Scripts\python.exe" main.py --web-server --no-display --weights models\best.onnx --port 5000

echo.
echo AquaCount has stopped. Count records are in output\runs
pause
