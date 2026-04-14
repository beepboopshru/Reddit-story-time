@echo off
echo Starting Reel Maker Web UI...

:: Change to the directory where this batch file is located
cd /d "%~dp0"

:: Run explicitly from the current repo venv
set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo .venv is missing at "%VENV_PYTHON%"
    pause
    exit /b 1
)

:: Change to the src directory
cd src

:: Open Microsoft Edge to the localhost address
echo Opening Edge to http://localhost:8000
start msedge http://localhost:8000

:: Start the FastAPI server
echo Starting Server...
"%VENV_PYTHON%" app.py

pause
