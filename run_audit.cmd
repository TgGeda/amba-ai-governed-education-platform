@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

if not exist "%CD%\src\" (
  echo [ERROR] Run this script from the repository root containing src\
  exit /b 1
)
if not exist "%CD%\kb\" (
  echo [ERROR] Run this script from the repository root containing kb\
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_audit.ps1" -ProjectRoot "%CD%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [ERROR] Project audit failed with exit code %RC%.
  exit /b %RC%
)

echo.
echo [OK] Audit completed successfully.
exit /b 0
