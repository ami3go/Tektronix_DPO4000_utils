#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="${APP_NAME:-TektronixScopeGUI}"
ENTRY_FILE="dpo4000_utils/gui/app.py"

if [[ ! -f "$ENTRY_FILE" ]]; then
  echo "ERROR: GUI entry file not found: $ENTRY_FILE" >&2
  exit 1
fi

echo "Cleaning old build output..."
rm -rf build dist "${APP_NAME}.spec"

echo "Installing build dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -e '.[build]'

echo "Building Linux one-file GUI executable..."
python3 -m PyInstaller \
  --onefile \
  --windowed \
  --clean \
  --name "$APP_NAME" \
  --collect-all dpo4000_utils \
  --collect-all pyvisa \
  --collect-all PIL \
  --hidden-import tkinter \
  --hidden-import tkinter.ttk \
  "$ENTRY_FILE"

chmod +x "dist/$APP_NAME"

echo
echo "Build finished: dist/$APP_NAME"
echo "NOTE: The target Linux PC still needs a VISA runtime/backend and Tk libraries installed."
