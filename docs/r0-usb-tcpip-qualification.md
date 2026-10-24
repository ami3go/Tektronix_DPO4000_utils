# R0 USB / TCPIP hardware performance qualification

Task: `DPO4000-R0-USB-TCPIP-QUALIFICATION-01`

**2026-10-24 outcome: BLOCKED — no authenticated physical DPO4054 USB/TCPIP
bench, independently authorized reversible writes, or measured transport artifacts
were available to this change.** This is software qualification support, not a
hardware performance certificate or an independent human approval.

## Risk and preflight

**Both** `capture_r0_baseline.py` and live `compare_r0_baseline.py`
intentionally change the oscilloscope setup. Read-only bench authorization is
**insufficient**. The operator must explicitly authorize reversible writes,
verify that a current setup is recoverable, and accept a verified restore plan.

1. Reserve exclusive ownership of the *same physical DPO4054* over USB and
   Ethernet; never assume that two addresses refer to the same scope.
2. Read `*IDN?` separately on each real, authenticated VISA resource and
   record the full response, serial number, firmware and installed options.
   Record VISA backend, operating system, Python/PyVISA and package versions.
3. Verify Probe Comp on CH1 where required. Document instrument limits,
   record lengths, other active clients and storage availability.
4. Verify that `*LRN?` or `SET?` returns a nonempty setup, that the
   setup can be restored on **this** scope, and that restoring this setup is
   approved. A setup string **does not recover REF waveform memory**.
5. Obtain written bench authorization before invoking either script with
   `--authorize-reversible-writes` and `--confirm-restore-plan`.
6. If restoration is not VERIFIED or unexpected behavior occurs, stop. The
   exclusive `r0_initial_setup.json` is retained for human-led recovery.

The guard snapshots the initial setup before changes and restores it within
`finally`-style context exit. It checks exact IDN and final setup readback;
failure returns nonzero, retains a failure report and prevents baseline
publication. Preserve `r0_setup_restoration.json` and both setup snapshots.

## Capture commands

Start with an **independently approved known-good commit** in a clean checkout
and use new, empty output directories. Full `*IDN?` strings and VISA resource
names below are **operator inputs**; no instrument connection is inferred.

```bash
# Verify USB resource and identity on a real DPO4054 before this step.
python scripts/capture_r0_baseline.py \
  --resource "$DPO4000_USB_RESOURCE" --expected-idn "$DPO4000_VERIFIED_IDN" \
  --output-dir qualification_reports/performance/usb/baseline \
  --authorize-reversible-writes --confirm-restore-plan \
  --reps-standard 20 --reps-heavy 5 --reps-waveform-large 5

# Repeat on the independently verified Ethernet resource.
python scripts/capture_r0_baseline.py \
  --resource "$DPO4000_TCPIP_RESOURCE" --expected-idn "$DPO4000_VERIFIED_IDN" \
  --output-dir qualification_reports/performance/tcpip/baseline \
  --authorize-reversible-writes --confirm-restore-plan \
  --reps-standard 20 --reps-heavy 5 --reps-waveform-large 5
```

Never overwrite or regenerate approved snapshots to remove a regression.
Record the six baseline SHA-256 hashes (functional, timing, extra metrics for
each transport) in the independently approved review record described below.

On the **exact candidate commit**, capture separately on USB and Ethernet:

```bash
python scripts/compare_r0_baseline.py \
  --resource "$DPO4000_USB_RESOURCE" --expected-idn "$DPO4000_VERIFIED_IDN" \
  --baseline-dir qualification_reports/performance/usb/baseline \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --output-dir qualification_reports/performance/usb/candidate \
  --authorize-reversible-writes --confirm-restore-plan

python scripts/compare_r0_baseline.py \
  --resource "$DPO4000_TCPIP_RESOURCE" --expected-idn "$DPO4000_VERIFIED_IDN" \
  --baseline-dir qualification_reports/performance/tcpip/baseline \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --output-dir qualification_reports/performance/tcpip/candidate \
  --authorize-reversible-writes --confirm-restore-plan
```

Candidate comparisons are fail-closed on identity, transport, restoration,
configuration, invalid/absent raw observations, unsupported mandatory waveform
sizes, missing thresholds, new/unqualified operations and performance regression.
A failure returns nonzero; inspect `comparison_report.json` and original
candidate observations before making any threshold proposal.

## Extra measured coverage (required, not synthesized)

The canonical R0 capture already times connection, identity, channel readback,
measurement setup, trigger apply/readback, acquisitions, screenshot/CSV and
waveforms. It records **actual monotonic samples** (`samples_s`),
sample count, p50/p95, maximum and standard deviation. With only five samples,
p99 is **null**, not a meaningful independent tail estimate.

Remaining **real measurements** are required on both known-good baseline and
candidate via independently executed harnesses with public API / installed CLI:

| Extra metric ID | Physical or application measurement |
| --- | --- |
| `transport_throughput` | Actual transferred wire bytes and elapsed read time; not inferred from NumPy array size |
| `a15_recipe_execution` | Real A15 recipe duration including per-step overhead |
| `a18_evidence_generation` | Real A18 evidence generation and durable completion |
| `a21_npz_export` | NPZ serialization + durable file size/time |
| `a21_dpoz_export` | DPOZ serialization + durable file size/time |
| `a25_headless_overhead` | Installed headless CLI startup/recipe overhead |
| `cancellation_and_error_recovery` | Actual cancellation and bounded recovery trials |
| `resource_usage` | Timed/observed resource growth plus host monitoring evidence |
| `gui_responsiveness` | Qt event-loop heartbeat/jitter while heavy operations execute |

For each transport and each baseline/candidate checkout, retain
`r0_extra_metrics.json` in the corresponding `baseline/` or `candidate/`
directory. Its structure is:

```json
{
  "schema_version": 1,
  "transport": "usb",
  "idn": "FULL VERIFIED IDN FROM THE BENCH",
  "commit_sha": "EXACT VERIFIED 40-DIGIT CHECKOUT COMMIT",
  "metrics": {
    "transport_throughput": {
      "sample_count": 0,
      "samples_s": [],
      "p50": null,
      "p95": null,
      "p99": null,
      "max": null,
      "payload_bytes": null
    }
  }
}
```

**This example is intentionally invalid** until real samples are provided.
The remaining metric IDs must each have the same observed distribution fields.
For NPZ/DPOZ add measured `file_bytes`; for throughput add actual
`payload_bytes`. Never fabricate observations or use estimated bytes as
network throughput. Record trials, errors/timeouts, backend, acquisition
settings and software versions in the bench log alongside the JSON. Capture
CPU/RSS/FD/thread evidence as appropriate.

The tool rejects absent metrics, missing or inconsistent raw samples, missing
approved thresholds and regressions. It cannot authenticate hardware or human
signatures. Update `NOT_YET_COVERED` only after real independently reviewed
harness coverage is implemented; deleting a gap text is not evidence.

## Independent approval and rollup

`tests/baselines/r0_timing_thresholds.json` currently contains historical
unreviewed defaults and is missing certain current timing operations. **No
thresholds were modified or approved by this task.** A qualified human
reviewer must approve the exact threshold SHA-256 and the exact six immutable
baseline file hashes. The operator must create
`qualification_reports/performance/threshold_review.json` only after real
measurements and independent review, using:

```json
{
  "status": "PENDING",
  "reviewer": "",
  "known_good_commit_sha": "",
  "threshold_sha256": "",
  "baseline_sha256": {}
}
```

The record above deliberately does **not** constitute approval. A reviewed
record must say `APPROVED`, identify a real reviewer, contain a matching
threshold SHA-256, a known-good SHA and one SHA-256 entry keyed by each of the
six baseline paths relative to `qualification_reports/performance/`. All
measured core/feature operations need explicit independently reviewed timing
limits. Do not loosen limits merely to obtain PASS.

```bash
python scripts/report_r0_transports.py \
  --root qualification_reports/performance \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --approval threshold_review.json
```

Output: `performance/transport_comparison/transport_comparison.json`,
`.csv`, `.md`, and optional USB/TCPIP p95 plots when measured rows exist
and matplotlib is installed. The CSV reports sample counts, p50/p95/p99,
max/stddev, absolute/relative regression, samples/s, and **measured** MB/s
where transferred byte counts exist. A nonzero exit means **BLOCKED/FAIL**.

The P0 release evaluator must also reject absent/non-PASS transport rollup
evidence. Keep human review/signoff and physical qualification separate from
software test status. No stable release may be declared on this offline report.
