#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_NAME="Difusion Legion"
SPEC_FILE="Difusion Legion macOS.spec"

echo
echo "==============================================="
echo " Difusion Legion - generar app para macOS"
echo "==============================================="
echo

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: no se encontro python3 para construir la app."
  echo "Instala Python 3 en la Mac de construccion y vuelve a ejecutar este script."
  exit 1
fi

"$PYTHON_BIN" -m venv .venv-build
source .venv-build/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements_build.txt

python tools/crear_icono_macos.py

rm -rf build dist
python -m PyInstaller --noconfirm --clean "$SPEC_FILE"

if command -v codesign >/dev/null 2>&1 && [ -d "dist/$APP_NAME.app" ]; then
  codesign --force --deep --sign - "dist/$APP_NAME.app" || true
fi

if command -v ditto >/dev/null 2>&1 && [ -d "dist/$APP_NAME.app" ]; then
  (
    cd dist
    rm -f "$APP_NAME-macOS.zip"
    ditto -c -k --sequesterRsrc --keepParent "$APP_NAME.app" "$APP_NAME-macOS.zip"
  )
fi

echo
echo "LISTO."
echo "App generada en:"
echo "$(pwd)/dist/$APP_NAME.app"
echo
echo "Zip opcional generado en:"
echo "$(pwd)/dist/$APP_NAME-macOS.zip"
echo
echo "La Mac que use la app no necesita Python. Si necesita tener Google Chrome o Microsoft Edge instalado."
