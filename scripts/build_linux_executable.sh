#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="${APP_NAME:-TektronixDPO4000}"
BUILD_MODE="${BUILD_MODE:-onedir}"
PYTHON_BIN="${PYTHON:-python3}"

if [[ "$BUILD_MODE" != "onedir" && "$BUILD_MODE" != "onefile" ]]; then
  echo "ERROR: BUILD_MODE must be onedir or onefile. Current value: ${BUILD_MODE}" >&2
  exit 1
fi

echo "Building ${APP_NAME} for Linux using PySide6 UI..."
echo "BUILD_MODE=${BUILD_MODE}"
echo "PYTHON=${PYTHON_BIN}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
  echo "Activate your virtual environment or set PYTHON=/path/to/python." >&2
  exit 1
fi

"$PYTHON_BIN" scripts/build_app.py --mode "$BUILD_MODE" --app-name "$APP_NAME" "$@"

if [[ "$*" == *"--dry-run"* ]]; then
  echo "Dry run completed; no executable was created."
  exit 0
fi

if [[ "$BUILD_MODE" == "onefile" ]]; then
  chmod +x "dist/${APP_NAME}"
  echo
  echo "Build finished: dist/${APP_NAME}"
else
  chmod +x "dist/${APP_NAME}/${APP_NAME}"
  echo
  echo "Build finished: dist/${APP_NAME}/${APP_NAME}"
fi

echo "NOTE: The target Linux PC still needs a VISA runtime/backend for real instrument access."
