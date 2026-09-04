from __future__ import annotations

from dpo4000_utils.logger.sync import CsvSyncPolicy


def test_csv_sync_policy_defaults_bound_fsync_frequency() -> None:
    policy = CsvSyncPolicy()
    assert policy.flush_every_records == 1
    assert policy.fsync_every_records == 50
    assert policy.fsync_interval_s == 5.0
    assert policy.fsync_on_close is True


def test_csv_sync_policy_rejects_invalid_values() -> None:
    for kwargs in (
        {"flush_every_records": 0},
        {"fsync_every_records": 0},
        {"fsync_interval_s": 0},
        {"fsync_interval_s": float("nan")},
    ):
        try:
            CsvSyncPolicy(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid sync policy accepted: {kwargs}")
