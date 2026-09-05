# PR #15 Follow-up Remediation Plan

Status: **In progress**
Baseline: **v0.6.72 / main after PR #15**

This plan closes the work intentionally left outside PR #15. It preserves the repository rule that the persistent-session runtime rewrite and the GUI composition rewrite are separate release milestones.

## Milestone A — v0.7.0: instrument runtime and qualification

### A1. Persistent worker-owned session becomes the production default
- Use one dedicated worker thread per DPO4000 Desk window.
- Create, use, reconnect, and close the DPO4054 on that owning thread.
- Keep transport/session configuration in the driver constructor/API; GUI worker code must not mutate the raw VISA handle.
- Invalidate and reopen the retained session after resource/transport definition changes or transport loss.
- Retain an explicit user reconnect action rather than silently creating one session per button press.

### A2. Remove nested Qt event loops
- Remove `QEventLoop.exec()` waits from scope action dispatch and persistent-session helpers.
- Submit actions asynchronously and complete them through Qt signals/callbacks.
- Serialize instrument operations; reject/queue conflicting requests rather than permitting re-entrant scope access.
- Keep all widget mutation on the GUI thread.

### A3. Safe cancellation and application shutdown
- Introduce cancellation tokens for cooperative long-running workflows.
- On window close, stop scheduling new work, request cancellation where supported, close the retained scope on its worker thread, then terminate the worker thread.
- Never terminate a QThread while VISA code is running.
- Bound shutdown and record a diagnostic if a backend operation cannot return before its driver timeout.

### A4. One coherent Core → REF → BUS refresh
- Execute the staged snapshot readers through one retained, already-connected driver instance.
- Preserve staged fault isolation and immediate Core-state projection.
- Do not reconnect between Core, REF and BUS stages.

### A5. Release reproducibility
- Add an exact release constraints file for build/runtime/test tooling.
- Make release build workflows install from that constraints set.
- Keep normal library metadata usable by downstream applications while documenting the reproducible release path.

### A6. Lint debt cleanup
- Remove the current per-file F401 allowances where the imports can be safely cleaned.
- Keep only deliberate compatibility exemptions.

### A7. Hardware qualification and soak tooling
- Keep the existing read-only/reversible/full hardware verifier.
- Add a repeatable 24 h / 72 h soak runner that records operation counts, reconnects, RSS/resource observations where available, failures, and final pass/fail criteria.
- Add a manual self-hosted workflow for the soak runner and retain its reports as artifacts.
- Physical DPO4054 execution remains a bench action; CI must not claim a hardware soak passed without a self-hosted result.

### A8. Decoded BUS extraction safety
- Do not invent undocumented decoder SCPI.
- Expose a capability contract that clearly reports decoded-event extraction as unavailable until a command path is hardware-qualified.
- Add a hardware-verification manifest entry so future implementation cannot bypass qualification.

### A9. Documentation
- Update current-state, architecture, build, verification and release guidance to describe the persistent worker runtime and exact dependency path.

## Milestone B — v0.8.0: Qt composition architecture

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
- Replace diagrams and text that still describe the historical inheritance chain or short-lived `scope_session()` GUI lifecycle.
- Record the final v0.8.0 composition boundaries and migration notes.

## Acceptance gates

Milestone A is complete when:
- no production scope action uses a nested `QEventLoop`;
- normal GUI actions reuse one worker-owned session;
- Core/REF/BUS refresh uses one connection;
- close during active work is safe and tested;
- exact release constraints are used by build workflows;
- Python 3.10–3.13 and PySide6 CI are green;
- the hardware verifier/soak workflow is ready for the self-hosted DPO4054 runner.

Milestone B is complete when:
- the launched GUI no longer depends on the historical multi-window inheritance chain;
- architecture CI enforces composition and the public-driver boundary;
- the full automated test matrix remains green.

## Hardware-only completion note

Code can make hardware qualification reproducible and mandatory, but it cannot truthfully mark the 24/72-hour DPO4054 soak as passed without an actual self-hosted bench run. The final merge/release checklist must link the corresponding hardware workflow artifact.