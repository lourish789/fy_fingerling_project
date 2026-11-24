@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  AquaCount - hatchery launcher (Windows). Double-click to start.
REM  Runs fully offline after the first run. App: http://localhost:5000
REM  Phones and tablets on the same Wi-Fi: use the "same Wi-Fi/LAN" address
REM  printed below, then "Install app" / "Add to Home Screen".
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
)

REM Install Python packages on the first run, and again whenever requirements-prod.txt changes.
fc /b requirements-prod.txt ".venv\requirements-prod.installed" >nul 2>&1
if errorlevel 1 (
  echo Installing Python packages. This needs internet once.
  ".venv\Scripts\python.exe" -m pip install -r requirements-prod.txt
  if errorlevel 1 (
    echo Package installation failed. Check the internet connection and try again.
    pause
    exit /b 1
  )
  copy /y requirements-prod.txt ".venv\requirements-prod.installed" >nul
)

if not exist "models\best.onnx" (
  echo models\best.onnx is missing. Copy the model file into the models folder.
  pause
  exit /b 1
)

REM The web app is built once (needs Node.js and internet), then served offline.
if not exist "web\dist\index.html" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo The web app has not been built, and Node.js is not installed.
    echo Install Node.js LTS from nodejs.org and run this again, or copy a built web\dist folder here.
    pause
    exit /b 1
  )
  echo First run: building the web app. This needs internet once.
  pushd web
  call npm ci
  if errorlevel 1 ( popd & echo Could not install the web app packages. & pause & exit /b 1 )
  call npm run build
  if errorlevel 1 ( popd & echo The web app build failed. & pause & exit /b 1 )
  popd
)

REM Open the app once the server has had a few seconds to load the model.
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:5000"

".venv\Scripts\python.exe" main.py --web-server --no-display --weights models\best.onnx --port 5000

echo.
echo AquaCount has stopped. Count records are in output\runs
pause
