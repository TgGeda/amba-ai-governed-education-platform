@echo off
setlocal EnableExtensions

rem ================================================================
rem Amba AI clean test runner
rem - Activates .venv when needed
rem - Adds src to PYTHONPATH
rem - Removes Python and pytest caches before and after testing
rem - Runs either the full test suite or caller-supplied pytest targets
rem - Preserves pytest's exit code
rem ================================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: %CD%\.venv
    echo Create it with: python -m venv .venv
    exit /b 2
)

set "PYTHONPATH=%CD%\src"
set "PYTHONDONTWRITEBYTECODE=1"

call :clean_caches
if errorlevel 1 (
    echo [ERROR] Pre-test cache cleanup failed.
    exit /b 3
)

echo.
echo [INFO] Python interpreter:
".venv\Scripts\python.exe" -c "import sys; print(sys.executable)"
if errorlevel 1 exit /b 4

echo.
if "%~1"=="" (
    echo [INFO] Running full test suite: tests
    ".venv\Scripts\python.exe" -m pytest tests -v
) else (
    echo [INFO] Running requested pytest arguments: %*
    ".venv\Scripts\python.exe" -m pytest %*
)

set "TEST_EXIT_CODE=%ERRORLEVEL%"

echo.
call :clean_caches
if errorlevel 1 (
    echo [WARNING] Post-test cache cleanup encountered an error.
    if "%TEST_EXIT_CODE%"=="0" set "TEST_EXIT_CODE=3"
)

echo.
if "%TEST_EXIT_CODE%"=="0" (
    echo [PASS] Test run completed successfully.
) else (
    echo [FAIL] Test run exited with code %TEST_EXIT_CODE%.
)

exit /b %TEST_EXIT_CODE%

:clean_caches
echo [INFO] Removing Python compilation and pytest caches...

for /d /r %%D in (__pycache__) do (
    if exist "%%D" rd /s /q "%%D"
)

for /r %%F in (*.pyc) do (
    if exist "%%F" del /f /q "%%F"
)

for /r %%F in (*.pyo) do (
    if exist "%%F" del /f /q "%%F"
)

if exist ".pytest_cache" rd /s /q ".pytest_cache"

rem Remove common coverage and type-checker caches when present.
if exist ".coverage" del /f /q ".coverage"
if exist ".coverage.*" del /f /q ".coverage.*" 2>nul
if exist "htmlcov" rd /s /q "htmlcov"
if exist ".mypy_cache" rd /s /q ".mypy_cache"
if exist ".ruff_cache" rd /s /q ".ruff_cache"

exit /b 0
