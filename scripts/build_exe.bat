@echo off
setlocal

set APP_NAME=TektronixScopeGUI
set MAIN_FILE=src\dpo4000_utils\gui\app.py
set ICON_FILE=src\dpo4000_utils\gui\dpo_scope_icon.ico

echo Cleaning old build output...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q %APP_NAME%.spec 2>nul

echo Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install -e .[build]

echo Building one-file EXE...
pyinstaller ^
  --onefile ^
  --windowed ^
  --clean ^
  --name %APP_NAME% ^
  --icon %ICON_FILE% ^
  --collect-all pyvisa ^
  --collect-all PIL ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  %MAIN_FILE%

echo.
echo Build finished: dist\%APP_NAME%.exe
pause
