@echo off
echo Starting Reel Maker Web UI...

:: Change to the directory where this batch file is located
cd /d "%~dp0"

:: Activate the virtual environment
call myenv\Scripts\activate.bat

:: Change to the src directory
cd src

:: Open the default web browser to the localhost address
echo Opening browser to http://localhost:8000
start http://localhost:8000

:: Start the FastAPI server
echo Starting Server...
python app.py

pause
