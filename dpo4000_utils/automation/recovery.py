"""Automation A11 retry/reconnect policy and statistics."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryPolicy:
    """Bounded transport-recovery policy for unattended Automation."""

    enabled: bool = True
    max_retries: int = 2
    retry_delay_s: float = 1.0
    max_consecutive_failures: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Automatic reconnect enabled flag must be boolean.")
        if isinstance(self.max_retries, bool):
            raise ValueError("Maximum retries must be a non-negative integer.")
        retries = int(self.max_retries)
        if float(self.max_retries) != float(retries) or retries < 0 or retries > 20:
            raise ValueError("Maximum retries must be an integer between 0 and 20.")
        delay = float(self.retry_delay_s)
        if not math.isfinite(delay) or delay < 0.1 or delay > 300.0:
            raise ValueError("Retry delay must be between 0.1 and 300 seconds.")
        if isinstance(self.max_consecutive_failures, bool):
            raise ValueError("Maximum consecutive failures must be a positive integer.")
        failures = int(self.max_consecutive_failures)
        if float(self.max_consecutive_failures) != float(failures) or failures < 1 or failures > 1000:
            raise ValueError("Maximum consecutive failures must be an integer between 1 and 1000.")
        object.__setattr__(self, "max_retries", retries)
        object.__setattr__(self, "retry_delay_s", delay)
        object.__setattr__(self, "max_consecutive_failures", failures)

    def delay_for_attempt(self, retry_number: int) -> float:
        """Return bounded linear backoff for retry #1..N."""
        retry = max(1, int(retry_number))
        return min(300.0, self.retry_delay_s * retry)


@dataclass
class RecoveryStatistics:
    retry_attempts: int = 0
    reconnects: int = 0
    transport_failures: int = 0
    consecutive_failures: int = 0
    last_error: str = ""

    def note_transport_failure(self, error: BaseException | str) -> None:
        self.transport_failures += 1
        self.last_error = str(error)

    def note_retry(self) -> None:
        self.retry_attempts += 1

    def note_reconnect_success(self) -> None:
        self.reconnects += 1
        self.consecutive_failures = 0
        self.last_error = ""

    def note_exhausted(self, error: BaseException | str) -> None:
        self.consecutive_failures += 1
        self.last_error = str(error)

    def note_normal_success(self) -> None:
        self.consecutive_failures = 0
        self.last_error = ""


__all__ = ["RecoveryPolicy", "RecoveryStatistics"]
