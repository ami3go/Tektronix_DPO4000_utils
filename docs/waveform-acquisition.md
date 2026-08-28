# Waveform Acquisition API

DPO4000 Utils v0.6.1 uses deterministic binary waveform transfer as the primary acquisition path.

## Transfer policy

Every `WaveformRequest` explicitly sets:

- `DATA:SOURCE`
- `DATA:START`
- `DATA:STOP`
- `DATA:WIDTH`
- `DATA:ENCDG`

The driver then reads back `DATA:START?` and `DATA:STOP?`, captures the outgoing waveform preamble before `CURVE?`, and validates the returned byte width, binary format, byte order, outgoing point count, point format, and X/Y scaling metadata.

For an explicit range, the scope must report exactly the requested start and stop. If the scope clips an explicit request, the driver raises `DPOWaveformError` instead of silently shortening the acquisition.

For a default full-waveform request, the driver writes `DATA:START 1` and an intentionally oversized `DATA:STOP`, then uses the scope-clipped `DATA:STOP?` value as the actual end of the record. This prevents a stale transfer window left by previous front-panel or SCPI activity from limiting a later default acquisition.

`WFMOutpre:NR_Pt?` is treated as the number of points in the currently selected outgoing transfer. It must equal the inclusive applied range `DATA:STOP - DATA:START + 1`; it is not interpreted as an absolute record stop index.

The default transfer format is `RIBINARY` with two-byte signed samples. On DPO4000-family oscilloscopes this is signed integer data with the most-significant byte transferred first.

ASCII is retained only as an explicit compatibility/debug option. DPO4000 ASCII `CURVE?` transfers above one million points are rejected locally because the programmer manual documents that limit.

## X-axis scaling

The DPO4000 outgoing preamble defines `XZERO` as the X coordinate of the first point in the outgoing waveform. Consequently a partial transfer does **not** add `DATA:START` to the X equation a second time.

For transferred sample index `i = 0..N-1`:

```text
X(i) = XZERO + XINCR * (i - PT_OFF)
```

The structured API stores the applied `start_index` / `stop_index` as transfer identity and validation metadata, but `WaveformData.time_at()` uses the outgoing-preamble coordinate system shown above.

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

To request the complete available record independent of previous `DATA:START/STOP` state:

```python
waveform = scope.read_channel_waveform_data(1)
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
- equal applied transfer ranges;
- equal X increment;
- equal X zero;
- equal point offset;
- equal X units.

A mismatch raises `DPOWaveformError` rather than silently truncating, overwriting, or misaligning data.

## Point formats

The v0.6 structured API accepts normal `PT_FMT=Y` waveforms. Envelope/min-max pair data (`PT_FMT=ENV`) is rejected explicitly because flattening those pairs into one voltage column would be ambiguous and unsafe. Use SAMPLE, HIRES, or AVERAGE acquisition when exporting through the current structured API.

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

For each run verify point count, first/last timestamps, and first/last scaled voltage are finite and consistent with the scope setup. The hardware suite also performs a small partial transfer and checks that successive timestamps are separated by `XINCR`, exercising the `XZERO`/partial-range semantics.

## Compatibility

The existing CSV methods remain available:

```python
scope.save_waveform_to_csv(1, "ch1.csv")
scope.save_all_channels_to_csv("capture")
scope.save_all_channels_to_single_csv("all.csv")
```

They use the deterministic binary structured acquisition internally.
