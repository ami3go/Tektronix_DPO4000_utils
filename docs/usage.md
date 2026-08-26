# Usage

## Desktop GUI

Install the package in editable mode, then start DPO4000 Desk:

```bash
pip install -e .[pyside6]
dpo4000-desk
```

The GUI opens VISA only during an operation and closes it afterwards. This is intentional so other software can access the oscilloscope while the GUI is idle.

## Python API

Use `dpo4000-utils` from scripts through the `dpo4000_utils` import package:

```python
from dpo4000_utils import DPO4054

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.set_record_length("10k")
    print(scope.get_record_length())
```

Record length accepts friendly labels for common settings and raw positive integer point counts:

```python
scope.set_record_length("1k")
scope.set_record_length("10k")
scope.set_record_length("100k")
scope.set_record_length("1M")
scope.set_record_length("10M")
scope.set_record_length(2500)
```

The generated SCPI command is `HORIZONTAL:RECORDLENGTH <points>`, and readback uses `HORIZONTAL:RECORDLENGTH?`.

## USB/VISA

Use the Connection page to refresh and select a VISA resource such as:

```text
USB0::0x0699::0x0401::C011280::INSTR
```

Manual entry is still available if discovery does not list the scope.

## Ethernet

Use the Ethernet mode in the Connection page. Try VXI-11 first:

```text
TCPIP0::<scope-ip>::INSTR
```

If VXI-11 is not available, try raw socket mode:

```text
TCPIP0::<scope-ip>::4000::SOCKET
```

## Output files

The File page controls the destination folder, filename prefix/base, and timestamp options for PNG screen captures, CSV waveform exports, and JSON setup files.

## Acquisition setup

The Acquisition page can read/apply acquisition mode, average count, and record length. Record length labels are converted to numeric point counts before being sent to the scope.
