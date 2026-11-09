@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
.venv\Scripts\python.exe tools\ui\run_submission_dashboard.py
exit /b %ERRORLEVEL%
