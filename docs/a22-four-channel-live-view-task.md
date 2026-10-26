# A22.1 Four-Channel Live View — v1.0 Implementation Task

Status: **SOFTWARE IMPLEMENTED — exact-head hardware qualification remains release-blocking**  
Priority: **P0 user-facing conformance gap**  
Depends on: existing A22 single-channel engine and DPO4054 waveform API  

## 1. Problem

The current A22 implementation is a technically useful single-channel streaming
prototype, but it does not provide the live oscilloscope-style experience intended
by the A22 plan:

- only one of CH1..CH4 can be selected at a time;
- the plot is placed inside a collapsed card at the bottom of Measurement;
- the plot occupies the narrow control panel instead of the main display area;
- there is no coherent four-channel frame, channel overlay, legend, grid, or
  per-channel presentation control;
- wording such as "CH1-CH4 streaming" can incorrectly imply simultaneous display.

For v1.0, A22 must provide a large live display on which all four analog channels
can be viewed together. The existing card must not be presented as completion of
that requirement.

## 2. Required user experience

Add a first-class **Live View** workspace to DPO4000 Desk.

1. The waveform canvas must occupy the main/left application viewport, normally
   at least 60% of the available window width and most of its usable height.
2. Live View controls may occupy the existing right control panel. Do not place
   the primary plot inside a collapsible control card.
3. Provide visible toggles for CH1, CH2, CH3, and CH4. Multiple channels, including
   all four, must be selectable at once.
4. Use stable, accessible channel identities and conventional colors:
   CH1 yellow, CH2 cyan, CH3 magenta, CH4 green. Color must not be the only means
   of identifying a trace; include a legend/label.
5. Show a scope-style graticule with a shared time axis and clearly labelled units.
6. Provide Start, Pause, Resume, Stop, and one-action Restart behavior.
7. Read each channel at the scope's own record length (no transfer-size selector; cap 1M samples) and provide a requested-rate control, but label the measured rate
   separately so a requested rate is never presented as achieved throughput.
8. Show actual group FPS, per-channel acquisition time, complete-cycle latency,
   frame age, transferred samples/bytes, dropped/replaced cycles, skipped
   deadlines, errors, and transport.
9. Show an explicit warning when fewer than the selected channels are returned,
   waveform metadata is incompatible, or inter-channel capture skew exceeds the
   reviewed threshold.
10. Persist channel visibility and presentation preferences without automatically
    changing scope channel, trigger, acquisition, record-length, or timebase state.

The static scope-screen Preview must remain available. Entering and leaving Live
View must switch the central viewport deterministically and must not destroy the
last captured preview.

## 3. Truthful meaning of "real time"

The DPO4000 public waveform path selects and transfers one waveform source at a
time. Four-channel Live View therefore consists of repeated, sequential reads
published as one completed **channel group**. It is not lossless ADC streaming and
must not claim that the four transfers were captured at the same instant.

For every displayed group retain:

- group sequence and generation;
- cycle start and completion monotonic timestamps;
- individual channel acquisition timestamps and durations;
- measured first-to-last channel skew;
- independent `WaveformData` metadata for every channel;
- the transport and requested point count.

Only publish a group after every selected channel has succeeded and alignment has
been validated. A failed or partial group must not combine new traces with stale
traces while presenting them as one frame. The previous complete group may remain
visible, clearly marked stale, while the error is shown.

## 4. Domain/API work

Extend the Qt-independent A22 model in `dpo4000_utils/live_stream.py` rather than
building multi-channel state in widgets.

Required model changes:

- replace the single `source` configuration with a non-empty, unique, ordered
  channel selection drawn from CH1..CH4;
- introduce an immutable multi-channel frame/group model;
- retain bounded render data per selected channel with a documented aggregate
  memory ceiling;
- keep exactly one complete group pending and at most one worker operation in
  flight;
- reset generation-local statistics on every restart;
- discard all late, partial, paused-generation, stopped-generation, and
  superseded completions;
- calculate group and per-channel throughput/latency/skew statistics;
- keep the domain model free of Qt and VISA imports.

The worker callback should call the existing public
`scope.read_enabled_waveforms(channels=..., point_count=...)` API, or an equally
public purpose-built driver method. Do not place source-selection SCPI in the GUI.
The public driver already validates waveform alignment; A22 must preserve and
surface that failure instead of weakening it.

Single-channel selection remains supported as a subset of the same group model.
Avoid parallel legacy and multi-channel schedulers.

## 5. Rendering requirements

- Render all selected traces on one shared time-axis canvas.
- Decimate each channel off the GUI thread using the existing spike-preserving
  min/max policy.
- Bound aggregate render points and paint time for four channels.
- Never convert or retain unbounded full-record float lists in the GUI.
- The GUI event thread must perform no VISA access or full-record decimation.
- Resize, expose, theme change, channel toggle, and legend updates must not start
  instrument reads.
- Support independent visual gain/offset or an explicit autoscale policy per
  channel. Presentation scaling must not write vertical settings to the scope.
- Display clipping, NaN/invalid metadata, and stale-data states visibly.

The canvas may use a carefully profiled Qt-native painter or a suitable plotting
component already acceptable to the project's offline packaging constraints. Do
not add a runtime dependency without validating Windows, Linux binary, AppImage,
deb, and Flatpak packaging.

## 6. Lifecycle and ownership

- Continue using the single retained scope worker/session.
- A complete four-channel cycle is one serialized A22 operation.
- Preserve the centralized A22 instrument lease: recipes, evidence capture,
  scientific export, logger ownership, and conflicting manual scope operations
  must be rejected while a cycle is active.
- Stop must invalidate publication immediately while retaining the physical lease
  until the worker callback returns or times out.
- Closing the application must stop scheduling and cannot wait on an infinite
  acquisition loop.
- Transport errors transition to an honest ERROR state. Automatic reconnect is
  out of scope unless separately designed and qualified.

## 7. Performance policy

Do not set a marketing FPS target before measurement. Establish and display
realistic performance separately for:

- USB and TCPIP/VXI-11;
- 1, 2, and 4 selected channels;
- 1k, 10k, 100k, and 1M points per channel;
- render budgets used by the production GUI.

The current single-channel results are a baseline, not a four-channel claim.
The implementation must remain responsive even when four-channel acquisition is
slow. A low honest group rate is acceptable; frozen UI, unbounded queues, mixed-age
groups, or incorrect rate labelling are not.

## 8. Tests

### Pure/domain tests

- configuration rejects empty, duplicate, unknown, or more-than-four sources;
- 1/2/4-channel complete groups preserve source identity and waveform metadata;
- partial group failure is never published;
- alignment failure is surfaced;
- one in-flight operation and one pending complete group remain invariant;
- latest-group replacement and statistics are deterministic under a fake clock;
- Stop/Pause/Restart discard stale or partial callbacks;
- four-channel 1M input respects documented raw and render memory bounds;
- per-channel decimation preserves positive and negative spikes.

### GUI tests

- instantiate the production `QtScopeWindow`, open Live View, and assert that the
  real large canvas and all four channel controls are present and visible;
- do not rely only on source-text or isolated-widget tests;
- verify the plot is in the central viewport, not the narrow Measurement card;
- exercise 1/2/4-channel Start/Pause/Resume/Stop with a fake serialized worker;
- prove a partial/late group cannot overwrite the displayed complete group;
- run a minimum 10-second synthetic four-channel stream with a 50 ms heartbeat
  and enforce a reviewed p95/max GUI-gap threshold;
- verify switching Preview <-> Live View preserves both states;
- verify application shutdown with an in-flight group.

### Regression/packaging tests

- Python 3.10-3.13 and Windows Python CI;
- offscreen PySide6 suite;
- PyInstaller startup and production-window integration;
- Windows ZIP, Linux binary, AppImage, deb, and Flatpak startup checks;
- ensure the built artifacts, not only the source checkout, expose Live View.

## 9. DPO4054 HIL qualification

Run against the exact release-candidate commit on both USB and TCP/IP:

1. verify the expected DPO4054 identity and selected transport;
2. snapshot the scope setup and DATA registers;
3. exercise 1, 2, and 4 enabled channels at 1k/10k/100k/1M;
4. retain raw per-channel/cycle timing, skew, sample count, alignment, memory,
   heartbeat, and throughput evidence;
5. exercise Pause/Resume, Stop during each source position, Restart, disconnect,
   and clean application close;
6. verify no mixed-generation or partial channel group is displayed;
7. verify the exact original scope setup is restored after every guarded leg;
8. compare USB and TCP/IP separately against reviewed baselines;
9. include representative four-channel operation in the formal 24-hour release
   soak and fail on errors, resource growth, worsening latency, or UI stalls.

If fewer than four physical channels are enabled, this must be reported accurately.
Qualification must deliberately enable/prepare all four channels under the approved
reversible-write procedure rather than counting a skipped four-channel case as a
pass.

## 10. Required documentation changes

- Update README wording to distinguish single-channel selection from concurrent
  four-channel display.
- Replace the obsolete claim that A22 remains only in an unmerged draft.
- Document measured group rates by transport, channel count, and point count.
- Document the sequential-transfer/skew limitation prominently.
- Add a screenshot of the production four-channel Live View from a packaged build.
- Update release notes and the A22 test matrix with exact-head evidence links.

## 11. Definition of done

A22.1 is complete only when all of the following are true:

- a normal user can open an obvious Live View and see CH1..CH4 together on a large
  central display without discovering a collapsed Measurement card;
- the implementation uses one bounded, Qt-independent multi-channel engine and
  the public driver API;
- the display never represents sequential transfers as simultaneous samples;
- unit, GUI, regression, and package tests pass on the exact candidate commit;
- USB and TCP/IP four-channel HIL matrices pass with retained evidence;
- the formal 24-hour soak includes representative four-channel streaming;
- documentation and release notes describe actual behavior and measured limits;
- independent release review approves the evidence with no open critical/high
  issue.

Until the exact-head HIL and soak criteria pass, A22.1 must be labelled
**software implemented, hardware qualification pending**, not release-qualified.
