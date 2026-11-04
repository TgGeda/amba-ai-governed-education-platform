#!/usr/bin/env bash
set -euo pipefail

echo "==================================================="
echo "  AmbaAI Enterprise Build Script (Linux/macOS)"
echo "==================================================="

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
OCR_PROJ_DIR="$ROOT_DIR/../AmbaOcr.Microservice"
DATA_BIN_DIR="$ROOT_DIR/data/bin/AmbaOcr"

echo "[1/5] Checking dependencies..."

command -v dotnet >/dev/null || { echo "[ERROR] dotnet not installed"; exit 1; }
command -v pyinstaller >/dev/null || { echo "[ERROR] pyinstaller not installed"; exit 1; }

echo "[2/5] Cleaning..."
rm -rf "$ROOT_DIR/build" "$ROOT_DIR/dist" "$DATA_BIN_DIR"
mkdir -p "$DATA_BIN_DIR"

echo "[3/5] Building OCR service (Windows target)..."

dotnet publish "$OCR_PROJ_DIR/AmbaOcr.Microservice.csproj" \
    -c Release \
    -r win-x64 \
    --self-contained true \
    -o "$DATA_BIN_DIR"

echo "[4/5] Packaging Python..."

cd "$ROOT_DIR"

if [ -f "amba_ai.spec" ]; then
    pyinstaller --clean --noconfirm amba_ai.spec
else
    pyinstaller \
        --clean \
        --noconfirm \
        --windowed \
        --name "AmbaAI" \
        --icon "assets/icon.icns" \
        --add-data "data:data" \
        --add-data "assets:assets" \
        "src/amba_ai/main.py"
fi

echo "[5/5] Build complete."
echo "Output: $ROOT_DIR/dist/AmbaAI"