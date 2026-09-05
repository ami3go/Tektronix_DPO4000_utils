# PR #15 Follow-up Remediation Plan

Status: **Milestone A software complete; Milestone B planned**
Baseline: **v0.6.72 / main after PR #15**
Milestone A target: **v0.7.0**

This plan closes the work intentionally left outside PR #15. It preserves the repository rule that the persistent-session runtime rewrite and the GUI composition rewrite are separate release milestones.

## Milestone A — v0.7.0: instrument runtime and qualification — COMPLETE

### A1. Persistent worker-owned session becomes the production default — DONE
- One dedicated worker thread owns the DPO4054 session for the launched DPO4000 Desk window.
- Driver creation, reuse, reconnect and close occur on the owning worker thread.
- Runtime transport configuration is exposed through the public driver API rather than raw GUI-owned VISA mutation.
- Transport/resource changes invalidate the retained session and reopen it cleanly.
- Session retention is the production default, with explicit reconnect/session controls retained.

### A2. Remove nested Qt event loops from production scope dispatch — DONE
- Scope actions complete through callbacks/signals instead of `QEventLoop.exec()` waits.
- Instrument operations remain serialized through the worker-owned session.
- Widget mutation remains on the GUI thread.
- The v0.7 launch shell also bypasses the legacy Logger health synchronous-return override.

### A3. Safe cancellation and application shutdown — DONE
- Long-running Automation/Logger operations use cooperative cancellation where supported.
- Window close stops new scheduling, requests cancellation, closes the retained scope on its worker thread and shuts down the worker safely.
- The Logger disk-writer shutdown uses a bounded wait in the launched v0.7 path and does not run a nested Qt event loop.
- No QThread is forcibly terminated while VISA work is executing.

### A4. One coherent Core → REF → BUS refresh — DONE
- Core, REF and BUS refresh stages execute as one ordered asynchronous chain.
- The same retained driver/session is preserved across the staged snapshot.
- Core projection and optional-stage fault isolation are retained.

### A5. Release reproducibility — DONE
- `constraints-release.txt` pins the release build/runtime/test toolchain.
- Release workflows install against the constraints set.
- Release artifacts retain the resolved dependency environment for provenance while normal package metadata remains usable downstream.

### A6. Lint debt cleanup — DONE
- The temporary PR #15 F401 per-file baseline has been removed.
- All safely removable deferred unused imports were deleted.
- The deliberate `tektronix_utils.py` compatibility re-export exemption remains.
- Ruff is green on the Milestone-A head.

### A7. Hardware qualification and soak tooling — SOFTWARE COMPLETE
- Existing read-only/reversible/full hardware verification remains available.
- A repeatable 24 h / 72 h soak runner records operation/reconnect/failure/resource observations and final criteria.
- A manual self-hosted DPO4000 soak workflow retains reports as GitHub Actions artifacts.
- **Bench-only pending item:** the physical DPO4054 24 h / 72 h PASS must be produced on the self-hosted instrument runner; software/CI does not fabricate this result.

### A8. Decoded BUS extraction safety — DONE
- No undocumented decoder SCPI was invented.
- Decoded-event extraction exposes an explicit unqualified capability contract.
- Hardware-verification coverage requires future decoded-event support to be deliberately qualified before it can be enabled.

### A9. Documentation — DONE
- Current state, architecture, build, hardware-verification and v0.7 release guidance describe the persistent asynchronous runtime and reproducible dependency path.

## Milestone-A acceptance evidence

Automated validation on PR #16 head includes:
- Ruff: PASS
- Core Python 3.10: PASS
- Core Python 3.11: PASS
- Core Python 3.12: PASS
- Core Python 3.13: PASS
- full PySide6 desktop GUI suite: PASS
- final launch-runtime contract tests: PASS

Additional v0.7 regression coverage enforces the asynchronous production gateway, bounded-writer Logger path, completion-time Automation retention/run-limit hooks, and absence of nested event-loop use in the launched Milestone-A shutdown override.

## Milestone B — v0.8.0: Qt composition architecture — PLANNED

### B1. Replace historical window inheritance as the production architecture
- Introduce one launched `QMainWindow` shell.
- Move page construction/behavior into composed page/controller objects with explicit dependencies.
- Move cross-cutting scope dispatch, preferences, logging and output-path services into composed services/controllers.
- Migrate one functional group at a time while preserving behavior tests.
- Keep legacy window modules only as temporary compatibility shims during migration; they must no longer be on the production launch MRO when the milestone is complete.

### B2. Strengthen architecture CI
- Assert the launched class has a shallow, intentional MRO.
- Recursively reject raw VISA/SCPI ownership from every Qt module.
- Assert page/controllers depend on the public driver/runtime facade rather than other historical window subclasses.

### B3. Final documentation cleanup
- Replace diagrams and text that still describe the historical inheritance chain.
- Record the final v0.8.0 composition boundaries and migration notes.

## Hardware-only completion note

Milestone A is software-complete. Physical qualification remains evidence generated by the bench, not by hosted CI. Before declaring the hardware qualification itself complete, run the self-hosted DPO4054 verification/soak workflow and retain the corresponding 24 h / 72 h artifact with the release records.
