@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python tools\setup.py
) else (
  py -3 tools\setup.py
)
if errorlevel 1 echo Setup failed. Python download: https://www.python.org/downloads/windows/
pause
