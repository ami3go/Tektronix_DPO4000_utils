# Current State Before Refactor

This refactor preserves the latest known GUI behavior from the v13 output-naming build:

- Connection tab with USB/VISA resource selection and Ethernet resource generation.
- Channel label read/write for CH1..CH4.
- Trigger tab with custom trigger level set/readback.
- Auto-scaled PNG preview.
- Robust screen PNG capture with Tektronix hardcopy payload extraction.
- CSV export for enabled channels.
- JSON save/restore for scope settings.
- Settings tab for output folder, per-file-type filename prefix/base, and timestamp options.
- Short-lived VISA sessions by default so the GUI does not keep the scope locked while idle.

This branch is intended as repository cleanup and packaging groundwork, not a full driver rewrite.
