# Waveform Acquisition API

DPO4000 Utils v0.6.0 uses deterministic binary waveform transfer as the primary acquisition path.

## Transfer policy

Every `WaveformRequest` explicitly sets:

- `DATA:SOURCE`
- `DATA:START`
- `DATA:STOP`
- `DATA:WIDTH`
- `DATA:ENCDG`

The driver then reads the complete outgoing waveform preamble before `CURVE?` and validates the returned byte width, binary format, byte order, record length, point format, and X/Y scaling metadata.

The default transfer format is `RIBINARY` with two-byte signed samples. On DPO4000-family oscilloscopes this is signed integer data with the most-significant byte transferred first.

ASCII is retained only as an explicit compatibility/debug option. DPO4000 ASCII `CURVE?` transfers above one million points are rejected locally because the programmer manual documents that limit.

## Structured API

```python
from dpo4000_utils import DPO4054, WaveformRequest

with DPO4054("USB0::...::INSTR", auto_connect=True) as scope:
    waveform = scope.read_waveform(
        WaveformRequest(
            source="CH1",
            start_index=1,
            point_count=100_000,
            encoding="RIBINARY",
            sample_width=2,
        )
    )

    print(waveform.source)
    print(waveform.label)
    print(waveform.sample_count)
    print(waveform.time_at(0), waveform.voltage_at(0))
```

For analog channels a convenience API is also available:

```python
waveform = scope.read_channel_waveform_data(1, point_count=10_000)
```

## Memory behavior

`WaveformData.samples` uses `array.array` and keeps compact integer samples rather than Python float objects. A 10-million-point, two-byte acquisition therefore keeps the stored sample payload near 20 MB.

Use these streaming methods for large records:

```python
waveform.iter_times()
waveform.iter_voltages()
waveform.time_at(index)
waveform.voltage_at(index)
```

`time_values()` and `voltage_values()` intentionally materialize 64-bit float arrays and therefore allocate additional memory.

Legacy tuple/list acquisition remains available through `_read_channel_waveform()` / `read_channel_waveform()` compatibility helpers, but those methods materialize Python lists and are not recommended for multi-million-point data.

## CSV integrity

Combined CSV export uses source identity as the internal key. User labels are display metadata only.

If CH1 and CH2 are both labelled `Voltage`, the combined CSV headers are deterministic and collision-free:

```text
Time (s),CH1 Voltage,CH2 Voltage
```

Before combined export the driver verifies:

- equal sample counts;
- equal transfer ranges;
- equal X increment;
- equal X zero;
- equal point offset;
- equal X units.

A mismatch raises `DPOWaveformError` rather than silently truncating, overwriting, or misaligning data.

## Point formats

The v0.6.0 structured API accepts normal `PT_FMT=Y` waveforms. Envelope/min-max pair data (`PT_FMT=ENV`) is rejected explicitly because flattening those pairs into one voltage column would be ambiguous and unsafe. Use SAMPLE, HIRES, or AVERAGE acquisition when exporting through the current structured API.

## Hardware qualification

Hardware tests are opt-in:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::...::INSTR' \
DPO4000_WAVEFORM_POINTS=1000 \
pytest -q -m hardware tests/hardware/test_scope_api_hardware.py
```

Repeat with:

```text
1000
10000
100000
<largest practical record length for the connected DPO4054/options>
```

For each run verify point count, first/last timestamps, and first/last scaled voltage are finite and consistent with the scope setup.

## Compatibility

The existing CSV methods remain available:

```python
scope.save_waveform_to_csv(1, "ch1.csv")
scope.save_all_channels_to_csv("capture")
scope.save_all_channels_to_single_csv("all.csv")
```

They now use the deterministic binary structured acquisition internally.
