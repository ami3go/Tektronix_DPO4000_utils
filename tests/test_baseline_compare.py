from __future__ import annotations

from dpo4000_utils.baseline_compare import (
    OperationThreshold,
    diff_functional,
    diff_timing,
    load_thresholds,
    regression_exit_code,
)


def _functional(**overrides):
    base = {
        "schema_version": 1,
        "commit_sha": "aaa",
        "captured_at": "2026-01-01T00:00:00+00:00",
        "package_version": "0.8.0",
        "python": "3.14.0",
        "platform": "Linux",
        "resource": "TCPIP0::x::INSTR",
        "idn": "TEKTRONIX,DPO4054,X,FV:v1.0",
        "firmware": "v1.0",
        "channels": {"1": {"display": "1", "scale": "0.5"}},
        "trigger": {"edge": {"source": "CH1"}},
    }
    base.update(overrides)
    return base


def test_diff_functional_ignores_metadata_only_differences():
    baseline = _functional()
    candidate = _functional(
        commit_sha="bbb", captured_at="2026-02-02T00:00:00+00:00", python="3.14.1"
    )
    assert diff_functional(baseline, candidate) == []


def test_diff_functional_detects_changed_leaf():
    baseline = _functional()
    candidate = _functional(channels={"1": {"display": "1", "scale": "1.0"}})

    diffs = diff_functional(baseline, candidate)

    assert len(diffs) == 1
    assert diffs[0].path == "channels.1.scale"
    assert diffs[0].kind == "changed"
    assert diffs[0].baseline == "0.5"
    assert diffs[0].candidate == "1.0"


def test_diff_functional_ignores_volatile_measurement_value_by_default():
    baseline = _functional(measurements={"1": {"slot": 1, "value": "9.9100E+37"}})
    candidate = _functional(measurements={"1": {"slot": 1, "value": "41.7195E+6"}})

    assert diff_functional(baseline, candidate) == []


def test_diff_functional_still_reports_measurement_config_changes():
    baseline = _functional(measurements={"1": {"slot": 1, "measurement_type": "FREQUENCY"}})
    candidate = _functional(measurements={"1": {"slot": 1, "measurement_type": "AMPLITUDE"}})

    diffs = diff_functional(baseline, candidate)

    assert len(diffs) == 1
    assert diffs[0].path == "measurements.1.measurement_type"


def test_diff_functional_detects_added_and_removed_keys():
    baseline = _functional(references={"1": {"display": "0"}})
    candidate = _functional()
    assert "references" not in candidate

    diffs = diff_functional(baseline, candidate)

    assert len(diffs) == 1
    assert diffs[0].path == "references"
    assert diffs[0].kind == "removed"
    assert diffs[0].baseline == {"1": {"display": "0"}}


def _stats(p95: float, **overrides):
    payload = {"min": p95 * 0.8, "p50": p95 * 0.9, "p95": p95, "p99": p95, "max": p95, "sample_count": 10}
    payload.update(overrides)
    return payload


def test_diff_timing_no_regression_when_within_both_limits():
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.05, relative_limit=1.30)}
    baseline_ops = {"connection": _stats(0.020)}
    candidate_ops = {"connection": _stats(0.021)}

    regressions, new_ops, missing_ops = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert len(regressions) == 1
    assert regressions[0].regressed is False
    assert new_ops == []
    assert missing_ops == []


def test_diff_timing_relative_exceeded_but_absolute_within_tolerance_is_not_regression():
    # 0.020 * 1.30 = 0.026 < 0.030 candidate -> relative exceeded
    # but 0.030 - 0.020 = 0.010 <= 0.05 absolute tolerance -> absolute NOT exceeded
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.05, relative_limit=1.30)}
    baseline_ops = {"connection": _stats(0.020)}
    candidate_ops = {"connection": _stats(0.030)}

    regressions, _, _ = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert regressions[0].relative_exceeded is True
    assert regressions[0].absolute_exceeded is False
    assert regressions[0].regressed is False


def test_diff_timing_absolute_exceeded_but_relative_within_limit_is_not_regression():
    # large baseline where a small absolute jump stays under the 1.30x relative limit
    thresholds = {"csv_export": OperationThreshold(absolute_tolerance_s=1.0, relative_limit=1.30)}
    baseline_ops = {"csv_export": _stats(30.0)}
    candidate_ops = {"csv_export": _stats(32.0)}  # +2s absolute, but 32 < 30*1.30=39

    regressions, _, _ = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert regressions[0].absolute_exceeded is True
    assert regressions[0].relative_exceeded is False
    assert regressions[0].regressed is False


def test_diff_timing_both_exceeded_is_a_regression():
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.001, relative_limit=1.10)}
    baseline_ops = {"connection": _stats(0.020)}
    candidate_ops = {"connection": _stats(0.050)}

    regressions, _, _ = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert regressions[0].relative_exceeded is True
    assert regressions[0].absolute_exceeded is True
    assert regressions[0].regressed is True


def test_diff_timing_flattens_waveform_acquisition_by_size():
    thresholds = {
        "waveform_acquisition.1000": OperationThreshold(absolute_tolerance_s=0.1, relative_limit=1.30)
    }
    baseline_ops = {"waveform_acquisition": {"1000": _stats(0.48)}}
    candidate_ops = {"waveform_acquisition": {"1000": _stats(0.49)}}

    regressions, new_ops, missing_ops = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert len(regressions) == 1
    assert regressions[0].operation == "waveform_acquisition.1000"
    assert new_ops == []
    assert missing_ops == []


def test_diff_timing_reports_new_and_missing_operations_without_regressing():
    baseline_ops = {"connection": _stats(0.02), "csv_export": _stats(30.0)}
    candidate_ops = {"connection": _stats(0.02), "png_capture": _stats(1.0)}
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.05)}

    regressions, new_ops, missing_ops = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert [r.operation for r in regressions] == ["connection"]
    assert new_ops == ["png_capture"]
    assert missing_ops == ["csv_export"]


def test_diff_timing_ignores_not_yet_covered_metadata_list():
    baseline_ops = {"connection": _stats(0.02), "not_yet_covered": ["logger throughput"]}
    candidate_ops = {"connection": _stats(0.02), "not_yet_covered": ["logger throughput"]}
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.05)}

    regressions, new_ops, missing_ops = diff_timing(baseline_ops, candidate_ops, thresholds)

    assert [r.operation for r in regressions] == ["connection"]
    assert new_ops == []
    assert missing_ops == []


def test_diff_timing_skips_operation_with_no_threshold():
    baseline_ops = {"unthresholded": _stats(1.0)}
    candidate_ops = {"unthresholded": _stats(10.0)}

    regressions, _, _ = diff_timing(baseline_ops, candidate_ops, thresholds={})

    assert regressions == []


def test_load_thresholds_parses_payload():
    payload = {
        "operations": {
            "connection": {"absolute_tolerance_s": 0.05, "relative_limit": 1.30},
            "csv_export": {"absolute_tolerance_s": 6.0},
        }
    }

    thresholds = load_thresholds(payload)

    assert thresholds["connection"] == OperationThreshold(absolute_tolerance_s=0.05, relative_limit=1.30)
    assert thresholds["csv_export"].relative_limit == 1.30  # default applied


def test_regression_exit_code_clean_run_is_zero():
    assert regression_exit_code([], []) == 0


def test_regression_exit_code_functional_diff_is_nonzero():
    diffs = diff_functional(_functional(), _functional(channels={"1": {"display": "0"}}))
    assert regression_exit_code(diffs, []) == 1


def test_regression_exit_code_timing_regression_is_nonzero():
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.001, relative_limit=1.10)}
    regressions, _, _ = diff_timing(
        {"connection": _stats(0.02)}, {"connection": _stats(0.05)}, thresholds
    )
    assert regression_exit_code([], regressions) == 1


def test_regression_exit_code_new_or_missing_operations_alone_is_zero():
    thresholds = {"connection": OperationThreshold(absolute_tolerance_s=0.05)}
    regressions, new_ops, missing_ops = diff_timing(
        {"connection": _stats(0.02), "csv_export": _stats(30.0)},
        {"connection": _stats(0.02), "png_capture": _stats(1.0)},
        thresholds,
    )
    assert new_ops and missing_ops
    assert regression_exit_code([], regressions) == 0
