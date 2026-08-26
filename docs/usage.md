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
    print(scope.query_identity())
```

DPO4000 Desk-supported controls are also available from the reusable API.

### Channel setup

```python
from dpo4000_utils import ChannelConfig, DPO4054

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.configure_channel(
        ChannelConfig(
            channel=1,
            display=True,
            scale="0.5",
            position="0",
            offset="0",
            coupling="DC",
            bandwidth="FULL",
            invert=False,
            probe_gain="10",
        )
    )
    print(scope.get_channel_configuration(1))
```

### MATH setup

```python
from dpo4000_utils import DPO4054, MathConfig

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.configure_math(MathConfig(display=True, define="CH1+CH2", scale="1", position="0"))
    print(scope.get_math_configuration())
```

### Measurement setup

```python
from dpo4000_utils import DPO4054
from dpo4000_utils.control import MeasurementConfig

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.add_measurement(MeasurementConfig(slot=1, measurement_type="FREQUENCY", source1="CH1"))
    print(scope.get_measurement_setup(1))
    print(scope.get_all_measurement_setups())
```

### Acquisition setup

```python
from dpo4000_utils import AcquisitionConfig, DPO4054

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.configure_acquisition(
        AcquisitionConfig(mode="AVERAGE", average_count=16, record_length="10k")
    )
    print(scope.get_acquisition_setup())
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

### Trigger and horizontal controls

```python
with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.configure_edge_trigger(
        source="CH1",
        slope="RISE",
        coupling="DC",
        mode="AUTO",
        level="1.0",
    )
    scope.set_horizontal_position(0)
    scope.run_acquisition()
    scope.force_trigger_event()
```

### Display, persistence, and screen text

```python
from dpo4000_utils import DisplayConfig, DPO4054

with DPO4054("USB0::0x0699::0x0401::C011280::INSTR", auto_connect=True) as scope:
    scope.apply_display_settings(
        DisplayConfig(
            backlight="80",
            waveform="70",
            graticule="40",
            persistence="AUTO",
            message_text="DPO4000 Desk",
            message_state=True,
        )
    )
    print(scope.get_display_settings())
    scope.clear_display_message()
```

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
