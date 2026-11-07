@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"

set "OUTPUT=%REPO_ROOT%\evidence\checksums\authoritative_source_verification.txt"

if not exist "%REPO_ROOT%\evidence\checksums" (
    mkdir "%REPO_ROOT%\evidence\checksums"
)

call "%SCRIPT_DIR%verify_authoritative_sources.cmd" > "%OUTPUT%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

>>"%OUTPUT%" echo verifier_exit_code=%EXIT_CODE%

type "%OUTPUT%"

exit /b %EXIT_CODE%