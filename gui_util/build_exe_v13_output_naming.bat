@echo off
set APP_NAME=TektronixScopeGUI
set MAIN_FILE=tektronix_scope_gui_v13_output_naming.py
set ICON_FILE=dpo_scope_icon.ico

echo Cleaning old build...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q %APP_NAME%.spec 2>nul

echo Installing build tools and Python dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller pyvisa pillow

echo Building one-file EXE...
pyinstaller ^
  --onefile ^
  --windowed ^
  --clean ^
  --name %APP_NAME% ^
  --icon %ICON_FILE% ^
  --add-data "%ICON_FILE%;." ^
  --collect-all pyvisa ^
  --collect-all PIL ^
  --hidden-import pyvisa ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageTk ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  --hidden-import tektronix_utils ^
  --hidden-import dpo4000_utils ^
  %MAIN_FILE%

echo.
echo Build finished.
echo EXE location:
echo dist\%APP_NAME%.exe
pause
