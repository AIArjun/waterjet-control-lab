@echo off
setlocal
cd /d "%~dp0"
set "LAB_PYTHON=%USERPROFILE%\.venvs\waterjet-lab\Scripts\python.exe"
if not exist "%LAB_PYTHON%" (
  echo Run Setup.cmd first.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8787 in your browser. Press Ctrl+C to stop.
"%LAB_PYTHON%" -m waterjet_lab.api
if errorlevel 1 pause
