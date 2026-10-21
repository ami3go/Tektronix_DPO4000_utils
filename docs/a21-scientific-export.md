# A21 Scientific Export

Status: **implemented on `a21-scientific-export`; software/HIL qualification pending**

A21 provides lossless, round-trippable scientific waveform export without moving instrument I/O into the export layer.

## Architecture boundary

A21 consumes already acquired `WaveformData` objects. It does not own VISA, SCPI, acquisition state, trigger state, or session lifecycle.

```text
DPO4000Scope.read_enabled_waveforms()
              |
              v
         WaveformData
              |
              v
     A21 scientific_export
       |               |
       v               v
     .npz             .dpoz
```

DPO4000 Desk captures enabled channels through the existing serialized scope worker and performs export in the same worker action. The Qt event loop never performs the waveform acquisition or large file write synchronously.

## Formats

### NumPy NPZ

Extension: `.npz`

Purpose: direct scientific-Python/Jupyter/NumPy use.

Each trace contains:

- exact raw sample array;
- derived float64 X array;
- derived float64 Y array.

The archive also contains a UTF-8 JSON manifest as a `uint8` array. Import uses `allow_pickle=False`; no pickle/object arrays are required or accepted.

NumPy is provided by the `scientific` extra and by the DPO4000 Desk (`pyside6`) extra. Release builds pin NumPy 2.2.6 because that series supports the project's Python 3.10–3.13 matrix.

### Portable DPOZ

Extension: `.dpoz` (ZIP container)

Purpose: dependency-light archival/interchange.

Contents:

```text
manifest.json
traces/000_CH1.raw
traces/000_CH1.csv
traces/001_CH2.raw
traces/001_CH2.csv
...
```

The raw payload is little-endian and preserves the source sample type exactly. CSV contains index, scaled X, and scaled Y values for use by spreadsheet/scientific tools without a custom reader.

## Lossless manifest

For every trace A21 stores:

- source;
- label;
- transfer start/stop;
- requested waveform encoding;
- acquisition timestamp;
- raw sample type and count;
- complete `WaveformPreamble`:
  - byte width;
  - encoding / binary format / byte order;
  - record point count / point format;
  - X unit, increment, zero, point offset;
  - Y unit, multiplier, offset, zero.

Dataset-level metadata is an arbitrary JSON object with finite numeric values.

Import reconstructs `WaveformData`, not merely a list of floats. Exact raw sample type/content and preamble are therefore available after round-trip.

## Atomic output

Export is transactional at file level:

1. create a temporary file in the destination directory;
2. completely write/close the archive;
3. atomically replace the destination with `os.replace()`;
4. remove the temporary file on failure.

An existing known-good destination therefore remains intact if export fails before finalization.

## Safety limits

- maximum 64 traces;
- maximum 100,000,000 total raw samples;
- manifest size capped at 1 MB during import;
- DPOZ raw payload byte size must exactly match manifest count/type;
- NPZ raw dtype/shape must exactly match the manifest;
- NPZ import always uses `allow_pickle=False`;
- unknown top-level/trace manifest fields are rejected;
- metadata mapping keys must be strings;
- all metadata floats, waveform scaling values, and floating raw samples must be finite;
- duplicate sources are rejected.

The importer never extracts archive paths to the filesystem; DPOZ members are addressed by deterministic names and read directly from the ZIP.

## Public API

```python
from dpo4000_utils import (
    export_scientific_dataset,
    import_scientific_dataset,
)

waveforms = scope.read_enabled_waveforms(point_count=100_000)
result = export_scientific_dataset(
    "capture.npz",
    waveforms,
    metadata={"test": "power-on transient"},
)
print(result.samples_per_second, result.megabytes_per_second)

loaded = import_scientific_dataset("capture.npz")
ch1 = loaded.dataset.by_source()["CH1"]
```

For headless users who only need A21/NumPy:

```bash
python -m pip install -e .[scientific]
```

## DPO4000 Desk

The existing File page is preserved and gains a `Scientific Export (A21)` panel with:

- format: NumPy NPZ / Portable DPOZ;
- record size: full / 1k / 10k / 100k / 1M points;
- optional compression;
- Export Enabled Channels action;
- completion status containing trace count, sample count, file size, duration, samples/s, and MB/s.

The panel uses only public `read_enabled_waveforms()` plus the framework-neutral exporter. It owns no raw SCPI/VISA handle.

## Performance qualification

`scripts/benchmark_a21_export.py` produces structured JSON for synthetic scaling runs. It records for each format/record size:

- samples;
- file bytes;
- export wall time;
- exporter-reported duration;
- samples/s;
- MB/s;
- peak traced Python memory;
- import wall time;
- import samples/s;
- import peak traced Python memory;
- exact round-trip result.

Default sizes are 1k, 10k, 100k, and 1M samples.

Example:

```bash
python scripts/benchmark_a21_export.py \
  --sizes 1000,10000,100000,1000000 \
  --formats npz,dpoz \
  --output a21-export-benchmark.json
```

Authoritative p50/p95/p99 and GUI-heartbeat gates remain controlled-runner metrics per `docs/regression-test-plan.md`; shared GitHub runners are used only for functional/scaling smoke tests.

## Hardware qualification

The focused DPO4054 HIL case:

1. connects to the expected DPO4054;
2. reads 1,000 CH1 waveform points through the public driver;
3. exports both NPZ and DPOZ;
4. imports both;
5. requires exact source/label/range/preamble/raw-sample round-trip.

A21 does not change trigger or acquisition configuration. Waveform transfer commands configure only the outgoing DATA transfer window/encoding as required by the existing waveform API.
