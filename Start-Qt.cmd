@echo off
setlocal
cd /d "%~dp0"
set "LAB_PYTHON=%USERPROFILE%\.venvs\waterjet-lab\Scripts\python.exe"
if not exist "%LAB_PYTHON%" (
  echo Run Setup.cmd first.
  pause
  exit /b 1
)
"%LAB_PYTHON%" -m waterjet_lab.desktop
if errorlevel 1 pause
