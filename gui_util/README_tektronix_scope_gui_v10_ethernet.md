# Tektronix DPO4054 Utility GUI - v10 Ethernet Support

This version adds Ethernet connection support while keeping the previous USB/VISA workflow.

## Connection modes

### USB / VISA resource

Use this for the existing USBTMC connection, for example:

```text
USB0::0x0699::0x0401::C011280::INSTR
```

Press **Refresh VISA list**, select the detected scope, then press **Test IDN**.

### Ethernet

Use this when the oscilloscope is connected through LAN.

The GUI can generate two VISA TCPIP resource forms:

```text
TCPIP0::<ip-address>::INSTR
TCPIP0::<ip-address>::4000::SOCKET
```

Recommended first attempt:

```text
VXI-11 / INSTR
```

Fallback if INSTR/VXI-11 is not detected by your VISA backend:

```text
Raw SOCKET, port 4000
```

Press **Use Ethernet resource**, then **Test IDN**.

## Main functions

- Read and set CH1..CH4 labels.
- Set and read trigger level.
- Capture current scope screen image as PNG.
- Auto-scale captured image preview.
- Save enabled channels to one CSV file.
- Save current scope settings to JSON.
- Restore saved scope settings from JSON.
- Use short-lived VISA sessions so the GUI does not hold the scope open while idle.

## Required files

Keep these files together:

```text
tektronix_scope_gui_v10_ethernet.py
tektronix_utils.py
dpo4000_utils.py
dpo_scope_icon.ico
```

## Run from Python

```bat
python tektronix_scope_gui_v10_ethernet.py
```

## Build EXE

```bat
build_exe_v10_ethernet.bat
```

The generated EXE does not require Python on the target PC, but the PC still needs a VISA backend/runtime for scope communication, such as NI-VISA, TekVISA, or Keysight VISA.
