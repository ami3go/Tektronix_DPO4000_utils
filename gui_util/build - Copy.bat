pyinstaller ^
  --onefile ^
  --windowed ^
  --clean ^
  --name TektronixScopeGUI ^
  --hidden-import pyvisa ^
  --hidden-import PIL ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageTk ^
  --hidden-import tektronix_utils ^
  tektronix_scope_gui_v7_tabs.py