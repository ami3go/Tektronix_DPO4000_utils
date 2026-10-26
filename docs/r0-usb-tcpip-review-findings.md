# R0 USB/Ethernet qualification — software reviewer findings

Task: `DPO4000-R0-USB-TCPIP-QUALIFICATION-01`
Date: 2026-10-24
PR: [#53](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/53)

**Review status: SOFTWARE REMEDIATION SUBMITTED / HARDWARE BLOCKED.**

This assessment is from automated source review and code changes. It is **not**
independent human safety signoff or a qualification certificate.

## Finding disposition

| Finding | Severity | Software action | Physical confirmation |
| --- | --- | --- | --- |
| Per-trial timing observations discarded | HIGH | Retain monotonic `samples_s`, mean/stddev, counts | BLOCKED |
| p99 generated for 1–5 repetitions | HIGH | p99 null until >=100 observations | BLOCKED |
| Waveform requested record truncated by existing length | HIGH | Request exact length and reject mismatch | BLOCKED |
| No whole-campaign initial/setup-restoration gate | CRITICAL | Exact-IDN setup guard, durable initial snapshot, postflight readback | BLOCKED |
| Functional setup round-trip hardcoded `restored=true` | HIGH | Require exact setup and identity equality | BLOCKED |
| New/unmeasured/under-thresholded operations could be tolerated | HIGH | Comparison fails on missing raw coverage, thresholds and operations | BLOCKED |
| Report omitted serialized `regressed` verdict | HIGH | Serialize and independently recompute regression decision | BLOCKED |
| Malformed/nonfinite acceptance limits could inhibit regression detection | HIGH | Enforce finite, nonnegative absolute and relative >=1 limits | BLOCKED |
| USB/TCPIP feature-level performance lacked a single auditable rollup | HIGH | Offline JSON/CSV/Markdown and optional plot tool, hashed approval contract | BLOCKED |
| P0 release gate did not require the transport rollup | HIGH | Require a reviewed PASS rollup plus baseline/candidate extra evidence | BLOCKED |

## Transport coverage disposition

These cells are **NOT MEASURED**, not zero elapsed time, not PASS.

| Required operation | USB | Ethernet | Software collection path |
| --- | --- | --- | --- |
| VISA connection and identity | BLOCKED | BLOCKED | R0 core timing |
| Channel/measurement reads | BLOCKED | BLOCKED | R0 core timing |
| Trigger setup/readback | BLOCKED | BLOCKED | R0 core timing |
| Acquisition synchronization | BLOCKED | BLOCKED | R0 core timing |
| 1k, 10k, 100k, 1M records | BLOCKED | BLOCKED | R0 core timing |
| Screenshot retrieval | BLOCKED | BLOCKED | R0 core timing |
| Actual wire throughput | BLOCKED | BLOCKED | Extra benchmark evidence |
| A15 recipe execution | BLOCKED | BLOCKED | Extra benchmark evidence |
| A18 bundle generation | BLOCKED | BLOCKED | Extra benchmark evidence |
| A21 NPZ / DPOZ | BLOCKED | BLOCKED | Extra benchmark evidence |
| A25 installed CLI overhead | BLOCKED | BLOCKED | Extra benchmark evidence |
| Cancellation and error recovery | BLOCKED | BLOCKED | Extra benchmark evidence |
| Resource usage | BLOCKED | BLOCKED | Extra benchmark evidence |
| GUI heartbeat under load | BLOCKED | BLOCKED | Extra benchmark evidence |

## Release decision

- No physical VISA connection, `*IDN?` response or hardware timing observation
  was obtained for this task.
- Neither USB nor Ethernet R0-F/R0-T reference snapshot was captured or
  independently approved.
- The historical threshold defaults were **not** widened or declared approved.
  New operations require explicit, separately reviewed limits.
- Source/unit test changes were submitted to existing draft PR #53, **not merged**.
  Final-head GitHub Actions and physical DPO4054 tests require separate review.
- The P0-G2 performance release gate remains **BLOCKED** until complete, signed,
  per-transport real evidence, matching physical identity, setup restoration,
  and independently approved baseline/threshold SHA-256 are reviewed.

See [operator procedure](r0-usb-tcpip-qualification.md) and
[unapproved reviewer template](r0-threshold-review-template.json).
