# Packaging on Windows

Use the provided script:

```bat
scripts\build_exe.bat
```

It builds a one-file executable with PyInstaller. The EXE includes Python and Python packages, but it does not include NI-VISA, TekVISA, Keysight VISA, or other system VISA runtimes. Install a VISA runtime separately on measurement PCs.

For debugging build issues, temporarily remove `--windowed` from the PyInstaller command so console errors are visible.
