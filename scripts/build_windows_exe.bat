@echo off
setlocal enableextensions

cd /d "%~dp0\.."

if not defined BUILD_MODE set "BUILD_MODE=onedir"
if not defined APP_NAME set "APP_NAME=TektronixDPO4000"

echo Building %APP_NAME% for Windows using PySide6 UI...
echo BUILD_MODE=%BUILD_MODE%

python --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found on PATH. Activate your venv or install Python first.
  exit /b 1
)

python scripts\build_app.py --mode "%BUILD_MODE%" --app-name "%APP_NAME%" %*
if errorlevel 1 exit /b 1

echo %* | findstr /C:"--dry-run" >nul
if not errorlevel 1 (
  echo Dry run completed; no executable was created.
  endlocal
  exit /b 0
)

echo.
if /i "%BUILD_MODE%"=="onefile" (
  echo Build finished: dist\%APP_NAME%.exe
) else (
  echo Build finished: dist\%APP_NAME%\%APP_NAME%.exe
)
echo NOTE: The target PC still needs a VISA runtime such as NI-VISA, TekVISA, or Keysight VISA.
endlocal
