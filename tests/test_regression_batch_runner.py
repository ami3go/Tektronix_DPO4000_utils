from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_regression_batch.py"
SPEC = importlib.util.spec_from_file_location("run_regression_batch", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_discovery_includes_all_named_regression_files_and_stress_suites() -> None:
    paths = MODULE.discover_regression_tests(ROOT)
    names = {path.name for path in paths}

    assert "test_regression_functional_snapshot.py" in names
    assert "test_regression_boundary_matrix.py" in names
    assert "test_regression_fake_io_latency.py" in names
    assert "test_regression_fault_latency.py" in names
    assert "test_regression_gui_responsiveness.py" in names
    assert "test_hardware_regression.py" in names
    assert "test_persistent_scope_stress.py" in names
    assert "test_logger_stress.py" in names
    assert all(path.is_file() for path in paths)


def test_software_command_uses_current_python_and_discovered_tests() -> None:
    command = MODULE.build_software_command()
    assert command[1:4] == ["-m", "pytest", "-q"]
    assert "tests/test_regression_metrics.py" in command
    assert "tests/test_hardware_regression.py" in command


def _args(mode: str) -> argparse.Namespace:
    return argparse.Namespace(
        hardware=mode,
        resource="TCPIP0::192.168.0.5::INSTR",
        channel=1,
        suite="all",
        waveform_points=1000,
        repetitions=5,
        skip_hardcopy=False,
        output_dir=Path("hardware_verification_reports/r0_probe_comp"),
        baseline=None,
        relative_limit=1.30,
        case_absolute_tolerance_s=0.25,
        total_absolute_tolerance_s=2.0,
        force_baseline=(mode == "create"),
    )


def test_create_hardware_command_forwards_baseline_safety_and_fixture_options() -> None:
    command = MODULE.build_hardware_command(_args("create"))
    assert "--create-baseline" in command
    assert "--compare-baseline" not in command
    assert "--force-baseline" in command
    assert command[command.index("--resource") + 1] == "TCPIP0::192.168.0.5::INSTR"
    assert command[command.index("--repetitions") + 1] == "5"


def test_compare_hardware_command_uses_same_baseline_path_without_force() -> None:
    command = MODULE.build_hardware_command(_args("compare"))
    assert "--compare-baseline" in command
    assert "--create-baseline" not in command
    assert "--force-baseline" not in command
    baseline = command[command.index("--baseline") + 1]
    assert baseline.endswith("r0_hardware_baseline.json")
