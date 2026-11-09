@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Missing .venv. Create it with: py -3.11 -m venv .venv
  echo Then install: .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
  exit /b 1
)

set "QT_QPA_PLATFORM="
set "PYTHONPATH=%CD%\src"

".venv\Scripts\python.exe" -m amba_ai.main
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%