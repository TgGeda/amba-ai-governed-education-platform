@echo off
cd /d F:\AmbaAI\amba_ai_project
call .venv\Scripts\activate
set PYTHONPATH=src
python -m amba_ai.main
pause