@echo off
setlocal enableextensions

cd /d "%~dp0\.."

set APP_NAME=TektronixScopeGUI
set ENTRY_FILE=dpo4000_utils\gui\app.py
set ICON_FILE=dpo4000_utils\gui\dpo_scope_icon.ico

if not exist "%ENTRY_FILE%" (
  echo ERROR: GUI entry file not found: %ENTRY_FILE%
  exit /b 1
)

if not exist "%ICON_FILE%" (
  echo WARNING: Icon file not found: %ICON_FILE%
  set ICON_ARGS=
) else (
  set ICON_ARGS=--icon "%ICON_FILE%"
)

echo Cleaning old build output...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q %APP_NAME%.spec 2>nul

echo Installing build dependencies...
py -3 -m pip install --upgrade pip
if errorlevel 1 exit /b 1

py -3 -m pip install -e .[build]
if errorlevel 1 exit /b 1

echo Building Windows one-file GUI executable...
py -3 -m PyInstaller ^
  --onefile ^
  --windowed ^
  --clean ^
  --name "%APP_NAME%" ^
  %ICON_ARGS% ^
  --collect-all dpo4000_utils ^
  --collect-all pyvisa ^
  --collect-all PIL ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  "%ENTRY_FILE%"
if errorlevel 1 exit /b 1

echo.
echo Build finished: dist\%APP_NAME%.exe
echo NOTE: The target PC still needs a VISA runtime such as NI-VISA, TekVISA, or Keysight VISA.
endlocal
