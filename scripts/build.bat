@echo off
setlocal EnableDelayedExpansion

echo ===================================================
echo   AmbaAI Enterprise Build Script (Windows)
echo ===================================================

:: Resolve paths
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..
set OCR_PROJ_DIR=%ROOT_DIR%\..\AmbaOcr.Microservice
set DATA_BIN_DIR=%ROOT_DIR%\data\bin\AmbaOcr

:: --------------------------------------------------
echo [1/5] Checking dependencies...
where dotnet >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] .NET SDK is not installed.
    exit /b 1
)

where pyinstaller >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller not found. Run: pip install pyinstaller
    exit /b 1
)

:: --------------------------------------------------
echo [2/5] Cleaning previous builds...
for %%d in ("%ROOT_DIR%\build" "%ROOT_DIR%\dist" "%DATA_BIN_DIR%") do (
    if exist "%%d" rd /s /q "%%d"
)

mkdir "%DATA_BIN_DIR%" >nul 2>nul

:: --------------------------------------------------
echo [3/5] Building OCR Microservice...

if not exist "%OCR_PROJ_DIR%\AmbaOcr.Microservice.csproj" (
    echo [ERROR] OCR project not found.
    exit /b 1
)

dotnet publish "%OCR_PROJ_DIR%\AmbaOcr.Microservice.csproj" ^
    -c Release ^
    -r win-x64 ^
    --self-contained true ^
    -o "%DATA_BIN_DIR%"

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] OCR build failed.
    exit /b %ERRORLEVEL%
)

:: --------------------------------------------------
echo [4/5] Building Python UI...

cd "%ROOT_DIR%"

if exist "amba_ai.spec" (
    pyinstaller --clean --noconfirm amba_ai.spec
) else (
    pyinstaller --noconfirm --clean ^
        --windowed ^
        --name "AmbaAI" ^
        --icon "assets\icon.ico" ^
        --add-data "data;data" ^
        --add-data "assets;assets" ^
        "src\amba_ai\main.py"
)

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller failed.
    exit /b %ERRORLEVEL%
)

:: --------------------------------------------------
echo [5/5] Build complete.
echo Output: %ROOT_DIR%\dist\AmbaAI
exit /b 0
