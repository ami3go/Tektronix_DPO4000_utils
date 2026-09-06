# Current State

As of **v0.7.0**, this repository has one desktop frontend: **DPO4000 Desk**, implemented with PySide6.

The reusable `dpo4000_utils` driver owns instrument communication and behavior. The launched desktop application uses one serialized, worker-owned DPO4054/VISA session by default and completes instrument operations asynchronously through Qt callbacks. The GUI thread does not wait for scope I/O through nested `QEventLoop` calls.

Current desktop capabilities include:

- USB/VISA and Ethernet resource selection.
- Persistent worker-owned connection reuse, with explicit per-operation reconnect compatibility mode.
- Safe transport invalidation/reconnect and cooperative shutdown/cancellation.
- Coherent staged Core → REF → BUS parameter refresh on one connection.
- CH1..CH4 labels and full channel configuration.
- MATH and REF1..REF4 configuration.
- BUS1..BUS4 configuration where exposed/licensed by the connected scope.
- Measurement management for MEAS1..MEAS8.
- Trigger and horizontal controls.
- Acquisition setup and run/stop/single/continuous actions.
- PNG capture/preview and full-record CSV waveform export.
- JSON scope setup save/restore.
- Front-panel display/persistence/message controls.
- Automation A1..A12, including periodic/triggered capture, waveform/measurement logging, conditional and burst workflows, retention, profiles, recovery and reports.
- Logger modes for waveform, measurements, decoded-BUS capability-gated input, and synchronized mixed records, with buffered/rotated output, recovery, health and reports.
- Streaming DPO4LOG inspection/conversion.
- Persistent output naming and connection preferences.

Decoded BUS transaction extraction remains explicitly capability-gated until a programmer-manual command path is qualified on real DPO4000 hardware. BUS configuration support does not imply decoded transaction export support.

Release builds use `constraints-release.txt` and publish the resolved Python dependency set with their artifacts so a shipped binary has an auditable build environment.

The former Tk frontend, its console entry point, archived Tk snapshots, and Tk-specific tests have been removed.

The historical PySide6 window-inheritance implementation remains behind the launched UI in v0.7.0. Its replacement with a composed shell/pages/controllers architecture is the separate v0.8.0 milestone.
