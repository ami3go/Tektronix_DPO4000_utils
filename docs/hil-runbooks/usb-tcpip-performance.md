# HIL-03 — Real DPO4054 USB and TCPIP R0-F/R0-T performance qualification

**State: TEMPLATE / NOT EXECUTED / BLOCKED until independent physical baselines and candidate evidence exist.** Both `capture_r0_baseline.py` and **live** `compare_r0_baseline.py` **write scope configuration**, so this is NOT a read-only campaign. See [global CI and PR closure](../ci-pr-closure-runbook.md), [performance evidence form](usb-tcpip-performance-evidence-template.md) and [canonical qualification contract](../r0-usb-tcpip-qualification.md).

## 1. Preflight and campaign identity

1. Complete software CI and explicitly authorized physical smoke first.
2. Reserve **one real DPO4054** for baseline and candidate runs; independently verify the actual USB resource and actual Ethernet resource refer to **the same device serial**. Do not substitute the sample addresses from docs. Never run USB and TCPIP sessions simultaneously.
3. Obtain operator authorization for **reversible scope writes**, independent full exact `*IDN?` including serial, backup `*LRN?`/`SET?` snapshot and an approved **verified restore plan**. REF waveform contents are not recovered by a setup string.
4. Identify known-good baseline SHA and target candidate full 40-digit SHA. Store the known-good reference in an immutable, separately reviewed directory; do not regenerate to hide a regression. Ensure identical fixture/probe and controlled conditions (CH1 Probe Comp where required).
5. Record VISA backend, instrument firmware/options, OS/Python/PyVISA/driver versions, requested channel/record length, actual waveform capability, repetitions, host loading and bench owner. Unsupported record sizes must be explicitly SKIP/coverage gaps, not PASS.
6. Obtain independent human approval of baseline SHA-256 hashes and threshold-file SHA-256; historic/default thresholds are not automatically approved.
7. Neither performance capture nor comparison currently has a standalone verified GitHub Actions workflow. **Execute on authorized bench under operator control**, then upload physical artifacts and job logs; hosted benchmarks remain synthetic.

## 2. Immutable baseline capture on approved known-good commit

Commands below are **real instrument operations**, not dry runs. Execute them only with actual verified values and approved reversible writes. Avoid changing between transport contexts without closing the prior session, verifying identity, and confirming setup restoration.

```bash
# FIRST: manually obtain operator approval and known-good checkout.
git checkout <APPROVED_KNOWN_GOOD_40_HEX_SHA>
export DPO4000_USB_RESOURCE="<VERIFIED_REAL_USB_VISA_RESOURCE>"
export DPO4000_TCPIP_RESOURCE="<VERIFIED_REAL_TCPIP_VISA_RESOURCE>"
export DPO4000_EXACT_IDN="<VERIFIED_FULL_IDN_INCLUDING_SERIAL>"

# USB baseline: store raw functional, raw timing and setup-restore evidence.
python scripts/capture_r0_baseline.py \
  --resource "$DPO4000_USB_RESOURCE" \
  --expected-idn "$DPO4000_EXACT_IDN" \
  --authorize-reversible-writes --confirm-restore-plan \
  --reps-standard 20 --reps-heavy 5 --reps-waveform-large 5 \
  --output-dir qualification_reports/performance/usb/baseline

# Confirm exact setup restoration and close the USB session before Ethernet.
python scripts/capture_r0_baseline.py \
  --resource "$DPO4000_TCPIP_RESOURCE" \
  --expected-idn "$DPO4000_EXACT_IDN" \
  --authorize-reversible-writes --confirm-restore-plan \
  --reps-standard 20 --reps-heavy 5 --reps-waveform-large 5 \
  --output-dir qualification_reports/performance/tcpip/baseline
```

**Mandatory baseline artifacts:** for *each* transport `r0_functional_baseline.json`, `r0_timing_baseline.json` and independently measured `r0_extra_metrics.json`. The extra metrics are **not automatically fully populated** by the baseline command: A15, A18, A21, A25, throughput, cancellation/recovery, resource usage and GUI heartbeat must be captured using reviewed real-device harnesses and the schema in `docs/r0-usb-tcpip-qualification.md`. Do not write dummy metrics with numeric values or claim they were measured.

Record SHA-256 of all six immutable baseline files and of `tests/baselines/r0_timing_thresholds.json`. An independent reviewer must approve the threshold set with all operations, tolerances and known-good source SHA in a retained `performance/threshold_review.json`; no self-approval. **STOP** if baseline files already exist and disagree, any restore is unverified, or raw timing coverage is missing.

## 3. Candidate capture / comparison at exact final PR or release SHA

```bash
git checkout <VERIFIED_FINAL_CANDIDATE_40_HEX_SHA>

python scripts/compare_r0_baseline.py \
  --baseline-dir qualification_reports/performance/usb/baseline \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --resource "$DPO4000_USB_RESOURCE" \
  --expected-idn "$DPO4000_EXACT_IDN" \
  --authorize-reversible-writes --confirm-restore-plan \
  --output-dir qualification_reports/performance/usb/candidate

# Verify restore/close before next physical transport.
python scripts/compare_r0_baseline.py \
  --baseline-dir qualification_reports/performance/tcpip/baseline \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --resource "$DPO4000_TCPIP_RESOURCE" \
  --expected-idn "$DPO4000_EXACT_IDN" \
  --authorize-reversible-writes --confirm-restore-plan \
  --output-dir qualification_reports/performance/tcpip/candidate

# After separately captured, real extra metrics and actual reviewer approval:
python scripts/report_r0_transports.py \
  --root qualification_reports/performance \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --approval threshold_review.json
```

Note: `--approval threshold_review.json` is resolved under the performance root by the rollup tool; the reviewer must provide the approved file (`qualification_reports/performance/threshold_review.json`) before this step. A comparison that fails for `NOT_YET_COVERED`, missing threshold or unsupported waveform size is **BLOCKED**; do not patch input JSON to fabricate coverage.

## 4. Required raw measurements and acceptance matrix

| Metric / check | Actual evidence required to PASS |
|---|---|
| Identity / transport | USB and TCPIP independent actual `*IDN?` and same verified device serial; matching backend/commit/fixture metadata |
| Functional R0-F | Measured public API operation outcomes, required case coverage, no hidden failure or unreviewed SKIP |
| Timing R0-T | Raw finite monotonic `samples_s` arrays and sample count; independently recomputed min/p50/p95/max and errors/timeouts |
| Waveform sizes | Physical 1k, 10k, 100k, **1M** records where required; stop or mark BLOCKED if scope record length/capability cannot supply it |
| Transport throughput | Actual wire bytes and measured elapsed transfer time; no inference from NumPy array size |
| Extra feature metrics | Real A15 recipe, A18 evidence, A21 NPZ/DPOZ, A25 installed CLI, cancellation/recovery, Qt heartbeat and resource-growth trials on both baseline and candidate |
| Baselines / thresholds | Six immutable baseline file SHA-256 values and approved threshold-file SHA-256; independent qualified reviewer record |
| Setup restoration | Initial and final scope setup snapshots; `VERIFIED`, zero unapproved residual changes |
| Comparison | `usb/candidate/comparison_report.json` and `tcpip/candidate/comparison_report.json` with PASS; no missing/new/unthresholded operations |
| Aggregate evidence | `performance/transport_comparison/transport_comparison.{json,csv,md}`, PASS with independently approved threshold provenance |
| Provenance | Both tested SHAs, actual HIL/operator logs, machine/backend info, artifacts/hashes, reviewer and UTC timestamps |

The rollup reports p95, sample counts, regressions and measured rate when byte counts are present. Sampled p99 must be omitted/null when insufficient samples; do not invent it. **Never compare USB baseline to TCPIP candidate**, reuse an old candidate after code changes, or loosen thresholds to force PASS.

## 5. Failure handling, output structure and review

Keep directories separate:

```text
qualification_reports/performance/
  threshold_review.json                         # only after real human approval
  usb/
    baseline/r0_functional_baseline.json
    baseline/r0_timing_baseline.json
    baseline/r0_extra_metrics.json
    candidate/r0_candidate_functional.json
    candidate/r0_candidate_timing.json
    candidate/r0_extra_metrics.json
    candidate/comparison_report.json
  tcpip/                                        # same structure, independent USB/TCPIP runs
  transport_comparison/
    transport_comparison.json
    transport_comparison.csv
    transport_comparison.md
```

For unexpected restore mismatch, missing real raw samples, unsupported options, excessive timeout, incomplete harness coverage or failed comparison: preserve evidence, stop further invasive tests, and record **FAIL/BLOCKED**. Re-run only after reviewing root cause and obtaining renewed operator approval. Do not hand-edit machine evidence or replace a reviewed baseline.

Fill [performance evidence form](usb-tcpip-performance-evidence-template.md), attach artifact hashes, independent review and the exact PR/release commit. This gate can only PASS for independently qualified actual USB **and** TCPIP captures; a green GitHub Actions synthetic benchmark is **NOT_RUN** as physical qualification.
