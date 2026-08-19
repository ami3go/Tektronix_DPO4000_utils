# Usage

## GUI

Install the package in editable mode, then start the GUI:

```bash
pip install -e .
dpo4000-gui
```

The GUI opens VISA only during an operation and closes it afterwards. This is intentional so other software can access the oscilloscope while the GUI is idle.

## USB/VISA

Use the Connection tab to refresh and select a VISA resource such as:

```text
USB0::0x0699::0x0401::C011280::INSTR
```

Manual entry is still available if discovery does not list the scope.

## Ethernet

Use the Ethernet mode in the Connection tab. Try VXI-11 first:

```text
TCPIP0::<scope-ip>::INSTR
```

If VXI-11 is not available, try raw socket mode:

```text
TCPIP0::<scope-ip>::4000::SOCKET
```

## Output files

The Settings tab controls the destination folder, filename prefix/base, and timestamp options for PNG screen captures, CSV waveform exports, and JSON setup files.
