@echo off
setlocal EnableExtensions
cd /d "%~dp0" || exit /b 1
set "PYTHONPATH=F:\AmbaAImba_ai_project\src;%PYTHONPATH%"
.venv\Scripts\python.exe -m amba_ai.cli.evidence_chain_demo %*
exit /b 0
