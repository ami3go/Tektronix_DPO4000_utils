#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="${APP_NAME:-TektronixDPO4000}"
BUILD_MODE="${BUILD_MODE:-onedir}"

echo "Building ${APP_NAME} for Linux using PySide6 UI..."
echo "BUILD_MODE=${BUILD_MODE}"

python3 scripts/build_app.py --mode "$BUILD_MODE" --app-name "$APP_NAME"

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
