# Current State

As of **v0.4.0**, this repository has one desktop frontend: **DPO4000 Desk**, implemented with PySide6.

The reusable `dpo4000_utils` driver owns instrument communication and behavior. The desktop application is a wrapper/orchestration layer over that API and uses short-lived `scope_session()` connections.

Current desktop capabilities include:

- USB/VISA and Ethernet resource selection.
- CH1..CH4 labels and channel configuration.
- Measurement management for MEAS1..MEAS8.
- Trigger and horizontal controls.
- Acquisition setup and run/stop/single/continuous actions.
- PNG capture/preview and CSV waveform export.
- JSON scope setup save/restore.
- Front-panel display/persistence/message controls.
- Persistent output naming and connection preferences.

The former Tk frontend, its console entry point, archived Tk snapshots, and Tk-specific tests have been removed.
