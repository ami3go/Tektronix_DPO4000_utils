"""A25 headless job runner reusing the A15/A16/A21 execution stack.

The runner validates all input before instrument I/O, owns one short-lived scope
session, executes the existing :class:`RecipeSequencer`, optionally evaluates an
A16 rule set and optionally emits an A21 scientific export.  It is intentionally
independent of Qt and does not create a second recipe/rule implementation.
"""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum, IntEnum
import json
import math
import os
from pathlib import Path
import signal
import sys
from tempfile import NamedTemporaryFile
import threading
import time
from typing import Any, Callable, Mapping

from .instrument import DPO4054
from .recipe import (
    Recipe,
    RecipeResult,
    RecipeRunState,
    RecipeSequencer,
    RecipeValidationError,
    recipe_from_mapping,
)
from .rules import (
    RuleEngine,
    RuleSet,
    RuleSetResult,
    RuleStatus,
    RuleValidationError,
    recipe_result_values,
    rule_set_from_mapping,
)
from .scientific_export import (
    MAX_SCIENTIFIC_SAMPLES,
    ScientificExportError,
    ScientificExportResult,
    ScientificFormat,
    export_scientific_dataset,
    infer_scientific_format,
    normalize_scientific_format,
)
from .session import scope_session

MAX_JOB_JSON_BYTES = 10_000_000
DEFAULT_JOB_TIMEOUT_MS = 20_000
MAX_JOB_TIMEOUT_MS = 600_000


class JobExitCode(IntEnum):
    SUCCESS = 0
    VALIDATION_ERROR = 2
    RUNTIME_ERROR = 3
    RECIPE_FAILED = 4
    RULE_FAILED = 5
    RULE_INVALID = 6
    EXPORT_ERROR = 7
    CANCELLED = 130


class JobValidationError(ValueError):
    """Raised before any instrument I/O when A25 input is invalid."""


@dataclass(frozen=True)
class JobConfig:
    recipe_path: Path
    resource: str | None = None
    rules_path: Path | None = None
    report_path: Path | None = None
    validate_only: bool = False
    timeout_ms: int = DEFAULT_JOB_TIMEOUT_MS
    expect_idn: str | None = None
    scientific_export_path: Path | None = None
    scientific_format: ScientificFormat | str | None = None
    scientific_points: int | None = None
    scientific_compressed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_path", Path(self.recipe_path))
        if self.rules_path is not None:
            object.__setattr__(self, "rules_path", Path(self.rules_path))
        if self.report_path is not None:
            object.__setattr__(self, "report_path", Path(self.report_path))
        if self.scientific_export_path is not None:
            object.__setattr__(
                self,
                "scientific_export_path",
                Path(self.scientific_export_path),
            )
        if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
            raise JobValidationError("timeout_ms must be an integer")
        if not 1 <= self.timeout_ms <= MAX_JOB_TIMEOUT_MS:
            raise JobValidationError(
                f"timeout_ms must be in range 1..{MAX_JOB_TIMEOUT_MS}"
            )
        resource = None if self.resource is None else str(self.resource).strip()
        object.__setattr__(self, "resource", resource or None)
        if not self.validate_only and not self.resource:
            raise JobValidationError("resource is required unless --validate-only is used")
        if self.expect_idn is not None:
            text = str(self.expect_idn).strip()
            object.__setattr__(self, "expect_idn", text or None)
        if self.scientific_points is not None:
            if (
                isinstance(self.scientific_points, bool)
                or not isinstance(self.scientific_points, int)
                or self.scientific_points <= 0
                or self.scientific_points > MAX_SCIENTIFIC_SAMPLES
            ):
                raise JobValidationError(
                    f"scientific_points must be a positive integer <= {MAX_SCIENTIFIC_SAMPLES}"
                )
        if not isinstance(self.scientific_compressed, bool):
            raise JobValidationError("scientific_compressed must be a boolean")
        if self.scientific_export_path is not None:
            if self.validate_only:
                raise JobValidationError("scientific export is not available in validate-only mode")
            try:
                selected = (
                    normalize_scientific_format(self.scientific_format)
                    if self.scientific_format is not None
                    else infer_scientific_format(self.scientific_export_path)
                )
            except ScientificExportError as exc:
                raise JobValidationError(str(exc)) from exc
            object.__setattr__(self, "scientific_format", selected)
        elif (
            self.scientific_format is not None
            or self.scientific_points is not None
            or self.scientific_compressed
        ):
            raise JobValidationError(
                "scientific format/points/compressed require scientific_export_path"
            )

        # Explicitly requested report/export destinations must never replace
        # the job's input recipe/rules or one another, including symlink aliases.
        input_paths = [
            path for path in (self.recipe_path, self.rules_path) if path is not None
        ]
        output_paths = [
            path for path in (self.report_path, self.scientific_export_path) if path is not None
        ]
        try:
            input_resolved = {path.resolve() for path in input_paths}
            output_resolved = [path.resolve() for path in output_paths]
        except (OSError, RuntimeError) as exc:
            raise JobValidationError(f"cannot resolve job file paths: {exc}") from exc
        if any(path in input_resolved for path in output_resolved):
            raise JobValidationError("report/export output path must not replace recipe/rules input")
        if len(output_resolved) != len(set(output_resolved)):
            raise JobValidationError("report and scientific export must have distinct paths")


@dataclass(frozen=True)
class JobResult:
    exit_code: JobExitCode
    status: str
    message: str
    started_at: datetime
    finished_at: datetime
    duration_s: float
    resource: str | None
    identity: str | None = None
    recipe_name: str | None = None
    recipe_result: RecipeResult | None = None
    rule_result: RuleSetResult | None = None
    scientific_export: ScientificExportResult | None = None
    validation_only: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code is JobExitCode.SUCCESS


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JobValidationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_json_mapping(path: str | Path, *, label: str) -> Mapping[str, Any]:
    source = Path(path)
    # Bounded binary read also protects against files enlarged after a stat call.
    try:
        with source.open("rb") as handle:
            raw = handle.read(MAX_JOB_JSON_BYTES + 1)
    except OSError as exc:
        raise JobValidationError(f"could not read {label} file {source}: {exc}") from exc
    if len(raw) > MAX_JOB_JSON_BYTES:
        raise JobValidationError(
            f"{label} file exceeds maximum of {MAX_JOB_JSON_BYTES:,} bytes"
        )

    def reject_constant(token: str) -> None:
        raise JobValidationError(f"non-standard JSON numeric constant: {token}")

    def bounded_int(token: str) -> int:
        if len(token) > 128:
            raise JobValidationError("JSON integer literal is excessively long")
        return int(token)

    def finite_float(token: str) -> float:
        number = float(token)
        if not math.isfinite(number):
            raise JobValidationError("JSON number is not finite")
        return number

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_object,
            parse_constant=reject_constant,
            parse_int=bounded_int,
            parse_float=finite_float,
        )
        # Python's JSON parser accepts escaped lone UTF-16 surrogates. Do not
        # allow ill-formed Unicode keys/values to reach the driver or report.
        json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        JobValidationError,
        RecursionError,
        ValueError,
    ) as exc:
        raise JobValidationError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise JobValidationError(f"{label} JSON must contain an object at the top level")
    return value


def load_job_inputs(config: JobConfig) -> tuple[Recipe, RuleSet | None]:
    try:
        recipe = recipe_from_mapping(load_json_mapping(config.recipe_path, label="recipe"))
        rules = (
            None
            if config.rules_path is None
            else rule_set_from_mapping(load_json_mapping(config.rules_path, label="rules"))
        )
    except (RecipeValidationError, RuleValidationError) as exc:
        raise JobValidationError(str(exc)) from exc
    return recipe, rules


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        stamp = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return {"type": type(value).__name__, "text": str(value)}


def job_result_to_mapping(result: JobResult) -> dict[str, Any]:
    return {
        "schema": "dpo4000-headless-job",
        "version": 1,
        "schema_version": 1,
        "exit_code": int(result.exit_code),
        "status": result.status,
        "message": result.message,
        "started_at": _json_safe(result.started_at),
        "finished_at": _json_safe(result.finished_at),
        "duration_s": result.duration_s,
        "resource": result.resource,
        "identity": result.identity,
        "recipe_name": result.recipe_name,
        "recipe_result": _json_safe(result.recipe_result),
        "rule_result": _json_safe(result.rule_result),
        "scientific_export": _json_safe(result.scientific_export),
        "validation_only": result.validation_only,
    }


def write_job_report(path: str | Path, result: JobResult) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
        delete=False,
    )
    temp = Path(handle.name)
    try:
        with handle:
            json.dump(job_result_to_mapping(result), handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, output)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        finally:
            raise
    return output


SessionFactory = Callable[..., AbstractContextManager[Any]]
TargetFactory = Callable[..., Any]


class HeadlessJobRunner:
    """Execute one validated A25 job with cooperative cancellation."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = scope_session,
        validation_target_factory: TargetFactory = DPO4054,
    ) -> None:
        self._session_factory = session_factory
        self._validation_target_factory = validation_target_factory
        self._cancel_requested = threading.Event()
        self._sequencer: RecipeSequencer | None = None
        self._run_lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel_requested.set()
        sequencer = self._sequencer
        if sequencer is not None:
            sequencer.cancel()

    def _preflight(self, recipe: Recipe, config: JobConfig) -> None:
        target = self._validation_target_factory(
            config.resource or "A25::VALIDATION_ONLY",
            auto_connect=False,
            timeout_ms=config.timeout_ms,
            read_termination="\n",
            write_termination="\n",
        )
        sequencer = RecipeSequencer(target)
        # Reuse A15's exact whole-recipe config-coercion/signature preflight. This
        # private helper performs no instrument I/O; A25 intentionally does not
        # duplicate those semantics in a second validator.
        sequencer._prepare_calls(recipe)

    @staticmethod
    def _result(
        *,
        started_at: datetime,
        started_perf: float,
        config: JobConfig,
        exit_code: JobExitCode,
        status: str,
        message: str,
        identity: str | None = None,
        recipe_name: str | None = None,
        recipe_result: RecipeResult | None = None,
        rule_result: RuleSetResult | None = None,
        scientific_export: ScientificExportResult | None = None,
    ) -> JobResult:
        finished_at = datetime.now(timezone.utc)
        return JobResult(
            exit_code=exit_code,
            status=status,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=max(0.0, time.perf_counter() - started_perf),
            resource=config.resource,
            identity=identity,
            recipe_name=recipe_name,
            recipe_result=recipe_result,
            rule_result=rule_result,
            scientific_export=scientific_export,
            validation_only=config.validate_only,
        )

    def run(self, config: JobConfig) -> JobResult:
        """Run at most one job at a time on this runner instance."""
        if not self._run_lock.acquire(blocking=False):
            now = datetime.now(timezone.utc)
            return JobResult(
                exit_code=JobExitCode.RUNTIME_ERROR,
                status="runtime_error",
                message="runner is already executing a job",
                started_at=now,
                finished_at=now,
                duration_s=0.0,
                resource=config.resource,
                validation_only=config.validate_only,
            )
        try:
            return self._run_exclusive(config)
        finally:
            self._run_lock.release()

    def _run_exclusive(self, config: JobConfig) -> JobResult:
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        identity: str | None = None
        recipe: Recipe | None = None
        recipe_result: RecipeResult | None = None
        rule_result: RuleSetResult | None = None
        scientific_result: ScientificExportResult | None = None

        try:
            recipe, rules = load_job_inputs(config)
            self._preflight(recipe, config)
            if self._cancel_requested.is_set():
                return self._result(
                    started_at=started_at,
                    started_perf=started_perf,
                    config=config,
                    exit_code=JobExitCode.CANCELLED,
                    status="cancelled",
                    message="Job cancelled during validation",
                    recipe_name=recipe.name,
                )
            if config.validate_only:
                return self._result(
                    started_at=started_at,
                    started_perf=started_perf,
                    config=config,
                    exit_code=JobExitCode.SUCCESS,
                    status="validated",
                    message="Recipe and optional rule set validated without instrument I/O",
                    recipe_name=recipe.name,
                )
            if self._cancel_requested.is_set():
                return self._result(
                    started_at=started_at,
                    started_perf=started_perf,
                    config=config,
                    exit_code=JobExitCode.CANCELLED,
                    status="cancelled",
                    message="Job cancelled before opening the instrument session",
                    recipe_name=recipe.name,
                )

            with self._session_factory(
                config.resource,
                timeout_ms=config.timeout_ms,
                read_termination="\n",
                write_termination="\n",
            ) as scope:
                identity = scope.query_identity()
                if config.expect_idn and config.expect_idn.upper() not in identity.upper():
                    raise RuntimeError(
                        f"scope identity {identity!r} does not contain expected {config.expect_idn!r}"
                    )
                if self._cancel_requested.is_set():
                    return self._result(
                        started_at=started_at,
                        started_perf=started_perf,
                        config=config,
                        exit_code=JobExitCode.CANCELLED,
                        status="cancelled",
                        message="Job cancelled before recipe execution",
                        identity=identity,
                        recipe_name=recipe.name,
                    )

                self._sequencer = RecipeSequencer(scope)

                def request_cancel_before_step(_index: int, _step: Any) -> None:
                    # A15 resets its own cancellation event on run(). The
                    # runner-owned event closes that pre-start cancellation race.
                    if self._cancel_requested.is_set():
                        self._sequencer.cancel()

                recipe_result = self._sequencer.run(
                    recipe, on_step_start=request_cancel_before_step
                )
                self._sequencer = None

                if (
                    recipe_result.state is RecipeRunState.CANCELLED
                    or self._cancel_requested.is_set()
                ):
                    return self._result(
                        started_at=started_at,
                        started_perf=started_perf,
                        config=config,
                        exit_code=JobExitCode.CANCELLED,
                        status="cancelled",
                        message="Recipe cancelled",
                        identity=identity,
                        recipe_name=recipe.name,
                        recipe_result=recipe_result,
                    )
                if recipe_result.state is RecipeRunState.FAILED:
                    return self._result(
                        started_at=started_at,
                        started_perf=started_perf,
                        config=config,
                        exit_code=JobExitCode.RECIPE_FAILED,
                        status="recipe_failed",
                        message=recipe_result.error or "Recipe failed",
                        identity=identity,
                        recipe_name=recipe.name,
                        recipe_result=recipe_result,
                    )

                if rules is not None:
                    rule_result = RuleEngine().evaluate(
                        rules,
                        recipe_result_values(recipe_result),
                    )

                if config.scientific_export_path is not None:
                    try:
                        waveforms = scope.read_enabled_waveforms(
                            point_count=config.scientific_points
                        )
                        scientific_result = export_scientific_dataset(
                            config.scientific_export_path,
                            waveforms,
                            format=config.scientific_format,
                            metadata={
                                "producer": "dpo4000-job",
                                "scope_identity": identity,
                                "recipe": recipe.name,
                                "rule_status": (
                                    None if rule_result is None else rule_result.status.value
                                ),
                            },
                            compressed=config.scientific_compressed,
                        )
                    except Exception as exc:
                        # A21 acquisition, filesystem and serializer errors are
                        # all export failures, not DUT rule failures.
                        return self._result(
                            started_at=started_at,
                            started_perf=started_perf,
                            config=config,
                            exit_code=JobExitCode.EXPORT_ERROR,
                            status="export_error",
                            message=str(exc),
                            identity=identity,
                            recipe_name=recipe.name,
                            recipe_result=recipe_result,
                            rule_result=rule_result,
                        )

            if self._cancel_requested.is_set():
                return self._result(
                    started_at=started_at,
                    started_perf=started_perf,
                    config=config,
                    exit_code=JobExitCode.CANCELLED,
                    status="cancelled",
                    message="Job cancelled after active operation returned",
                    identity=identity,
                    recipe_name=recipe.name,
                    recipe_result=recipe_result,
                    rule_result=rule_result,
                    scientific_export=scientific_result,
                )

            if rule_result is not None:
                if rule_result.status is RuleStatus.FAIL:
                    return self._result(
                        started_at=started_at,
                        started_perf=started_perf,
                        config=config,
                        exit_code=JobExitCode.RULE_FAILED,
                        status="rule_failed",
                        message="A16 rule set evaluated to FAIL",
                        identity=identity,
                        recipe_name=recipe.name,
                        recipe_result=recipe_result,
                        rule_result=rule_result,
                        scientific_export=scientific_result,
                    )
                if rule_result.status is RuleStatus.INVALID:
                    return self._result(
                        started_at=started_at,
                        started_perf=started_perf,
                        config=config,
                        exit_code=JobExitCode.RULE_INVALID,
                        status="rule_invalid",
                        message="A16 rule set evaluated to INVALID",
                        identity=identity,
                        recipe_name=recipe.name,
                        recipe_result=recipe_result,
                        rule_result=rule_result,
                        scientific_export=scientific_result,
                    )

            return self._result(
                started_at=started_at,
                started_perf=started_perf,
                config=config,
                exit_code=JobExitCode.SUCCESS,
                status="pass" if rule_result is not None else "completed",
                message=(
                    "A16 rule set evaluated to PASS"
                    if rule_result is not None
                    else "Recipe completed"
                ),
                identity=identity,
                recipe_name=recipe.name,
                recipe_result=recipe_result,
                rule_result=rule_result,
                scientific_export=scientific_result,
            )
        except (JobValidationError, RecipeValidationError, RuleValidationError) as exc:
            return self._result(
                started_at=started_at,
                started_perf=started_perf,
                config=config,
                exit_code=JobExitCode.VALIDATION_ERROR,
                status="validation_error",
                message=str(exc),
                recipe_name=None if recipe is None else recipe.name,
            )
        except KeyboardInterrupt:
            self.cancel()
            return self._result(
                started_at=started_at,
                started_perf=started_perf,
                config=config,
                exit_code=JobExitCode.CANCELLED,
                status="cancelled",
                message="Interrupted",
                identity=identity,
                recipe_name=None if recipe is None else recipe.name,
                recipe_result=recipe_result,
                rule_result=rule_result,
                scientific_export=scientific_result,
            )
        except Exception as exc:
            return self._result(
                started_at=started_at,
                started_perf=started_perf,
                config=config,
                exit_code=JobExitCode.RUNTIME_ERROR,
                status="runtime_error",
                message=f"{type(exc).__name__}: {exc}",
                identity=identity,
                recipe_name=None if recipe is None else recipe.name,
                recipe_result=recipe_result,
                rule_result=rule_result,
                scientific_export=scientific_result,
            )
        finally:
            self._sequencer = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dpo4000-job",
        description="Run a validated DPO4000 recipe without the Qt desktop application.",
    )
    parser.add_argument("--recipe", type=Path, required=True, help="A15 recipe JSON")
    parser.add_argument("--rules", type=Path, help="optional A16 rules JSON")
    parser.add_argument(
        "--resource",
        default=os.getenv("DPO4000_RESOURCE"),
        help="VISA resource (CLI > DPO4000_RESOURCE > no default)",
    )
    parser.add_argument("--report", type=Path, help="atomic JSON result report path")
    parser.add_argument("--validate-only", action="store_true", help="validate without opening VISA")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=None,
        help="VISA timeout in ms (CLI > DPO4000_TIMEOUT_MS > 20000; range 1..600000)",
    )
    parser.add_argument(
        "--expect-idn",
        help="required case-insensitive *IDN? substring (CLI > DPO4000_EXPECT_IDN)",
    )
    parser.add_argument("--export", dest="scientific_export_path", type=Path)
    parser.add_argument("--export-format", choices=("npz", "dpoz"))
    parser.add_argument("--export-points", type=int, dest="scientific_points")
    parser.add_argument("--export-compressed", action="store_true", dest="scientific_compressed")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        timeout_ms = args.timeout_ms
        if timeout_ms is None:
            timeout_env = os.getenv("DPO4000_TIMEOUT_MS")
            if timeout_env is None:
                timeout_ms = DEFAULT_JOB_TIMEOUT_MS
            else:
                try:
                    timeout_ms = int(timeout_env)
                except ValueError as exc:
                    raise JobValidationError(
                        "DPO4000_TIMEOUT_MS must be a decimal integer"
                    ) from exc
        expect_idn = (
            args.expect_idn
            if args.expect_idn is not None
            else os.getenv("DPO4000_EXPECT_IDN")
        )
        config = JobConfig(
            recipe_path=args.recipe,
            resource=args.resource,
            rules_path=args.rules,
            report_path=args.report,
            validate_only=args.validate_only,
            timeout_ms=timeout_ms,
            expect_idn=expect_idn,
            scientific_export_path=args.scientific_export_path,
            scientific_format=args.export_format,
            scientific_points=args.scientific_points,
            scientific_compressed=args.scientific_compressed,
        )
    except (JobValidationError, ScientificExportError) as exc:
        now = datetime.now(timezone.utc)
        invalid = JobResult(
            exit_code=JobExitCode.VALIDATION_ERROR,
            status="validation_error",
            message=str(exc),
            started_at=now,
            finished_at=now,
            duration_s=0.0,
            resource=args.resource,
            validation_only=args.validate_only,
        )
        if args.report is not None:
            try:
                write_job_report(args.report, invalid)
            except OSError as report_exc:
                if not args.quiet:
                    print(f"Could not write report: {report_exc}", file=sys.stderr)
                return int(JobExitCode.RUNTIME_ERROR)
        if not args.quiet:
            print(json.dumps(job_result_to_mapping(invalid), sort_keys=True))
        return int(JobExitCode.VALIDATION_ERROR)

    runner = HeadlessJobRunner()
    interrupt_count = 0
    previous_handler = signal.getsignal(signal.SIGINT)

    def handle_sigint(_signum, _frame) -> None:
        nonlocal interrupt_count
        interrupt_count += 1
        if interrupt_count == 1:
            runner.cancel()
            if not args.quiet:
                print("Cancellation requested; waiting for the active driver call to return.", file=sys.stderr)
            return
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handle_sigint)
    try:
        result = runner.run(config)
    finally:
        signal.signal(signal.SIGINT, previous_handler)

    if config.report_path is not None:
        try:
            write_job_report(config.report_path, result)
        except Exception as exc:
            if not args.quiet:
                print(f"Could not write report: {exc}", file=sys.stderr)
            # An explicitly requested report is part of the job contract.
            # Its failure must not masquerade as a DUT PASS/FAIL.
            return int(JobExitCode.RUNTIME_ERROR)

    if not args.quiet:
        print(json.dumps(job_result_to_mapping(result), sort_keys=True))
    return int(result.exit_code)


__all__ = [
    "DEFAULT_JOB_TIMEOUT_MS",
    "HeadlessJobRunner",
    "JobConfig",
    "JobExitCode",
    "JobResult",
    "JobValidationError",
    "job_result_to_mapping",
    "load_job_inputs",
    "load_json_mapping",
    "main",
    "write_job_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
