"""Real-hardware verification runner for the public DPO4000 API.

This module intentionally lives outside the normal driver execution path. It
reflects the public DPO4000Scope API, runs registered bench checks, restores the
initial instrument setup after write-capable profiles, and emits Markdown/JSON/
HTML evidence.
"""

from __future__ import annotations

import html
import inspect
import json
import platform
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from importlib import metadata
from pathlib import Path
from typing import Any

import dpo4000_utils as public_api

from .bus import BusConfig
from .control import (
    AcquisitionConfig,
    ChannelConfig,
    DisplayConfig,
    MathConfig,
    MeasurementConfig,
    bool_from_scope_response,
)
from .hardcopy import PNG_SIGNATURE
from .instrument import DPO4054, DPO4000Scope
from .reference import ReferenceConfig
from .settings import apply_setup_string, build_scope_settings_payload
from .waveform import WaveformRequest


class VerificationRisk(IntEnum):
    READ_ONLY = 0
    REVERSIBLE = 1
    DISRUPTIVE = 2


RISK_LABELS = {
    VerificationRisk.READ_ONLY: "read-only",
    VerificationRisk.REVERSIBLE: "reversible",
    VerificationRisk.DISRUPTIVE: "disruptive",
}


class VerificationSkip(RuntimeError):
    """Raised by one verification case when hardware capability is unavailable."""


@dataclass(frozen=True)
class VerificationCase:
    case_id: str
    title: str
    risk: VerificationRisk
    covers_methods: tuple[str, ...] = ()
    covers_functions: tuple[str, ...] = ()


@dataclass
class VerificationResult:
    case_id: str
    title: str
    risk: str
    status: str
    duration_s: float
    covers_methods: list[str] = field(default_factory=list)
    covers_functions: list[str] = field(default_factory=list)
    detail: str = ""
    error_type: str = ""
    error_message: str = ""


PUBLIC_METHOD_RISK: dict[str, VerificationRisk] = {
    "connect": VerificationRisk.READ_ONLY,
    "disconnect": VerificationRisk.READ_ONLY,
    "ensure_connected": VerificationRisk.READ_ONLY,
    "temporary_timeout": VerificationRisk.READ_ONLY,
    "query_identity": VerificationRisk.READ_ONLY,
    "get_channel_label": VerificationRisk.READ_ONLY,
    "get_channel_labels": VerificationRisk.READ_ONLY,
    "get_ch_max": VerificationRisk.REVERSIBLE,
    "set_channel_label": VerificationRisk.REVERSIBLE,
    "get_measurement_setup": VerificationRisk.READ_ONLY,
    "get_all_measurement_setups": VerificationRisk.READ_ONLY,
    "read_measurement_value": VerificationRisk.READ_ONLY,
    "add_measurement": VerificationRisk.REVERSIBLE,
    "disable_measurement": VerificationRisk.REVERSIBLE,
    "disable_all_measurements": VerificationRisk.DISRUPTIVE,
    "get_channel_configuration": VerificationRisk.READ_ONLY,
    "configure_channel": VerificationRisk.REVERSIBLE,
    "get_math_configuration": VerificationRisk.READ_ONLY,
    "configure_math": VerificationRisk.REVERSIBLE,
    "get_horizontal_position": VerificationRisk.READ_ONLY,
    "set_horizontal_position": VerificationRisk.REVERSIBLE,
    "nudge_horizontal_position": VerificationRisk.REVERSIBLE,
    "get_acquisition_setup": VerificationRisk.READ_ONLY,
    "get_acquisition_state": VerificationRisk.READ_ONLY,
    "is_acquiring": VerificationRisk.READ_ONLY,
    "get_trigger_state": VerificationRisk.READ_ONLY,
    "get_acquisition_mode": VerificationRisk.READ_ONLY,
    "get_average_count": VerificationRisk.READ_ONLY,
    "get_record_length": VerificationRisk.READ_ONLY,
    "configure_acquisition": VerificationRisk.REVERSIBLE,
    "set_acquisition_mode": VerificationRisk.REVERSIBLE,
    "set_average_count": VerificationRisk.REVERSIBLE,
    "set_record_length": VerificationRisk.REVERSIBLE,
    "run_acquisition": VerificationRisk.DISRUPTIVE,
    "stop_acquisition": VerificationRisk.DISRUPTIVE,
    "single_acquisition": VerificationRisk.DISRUPTIVE,
    "continuous_acquisition": VerificationRisk.DISRUPTIVE,
    "get_trigger_level": VerificationRisk.READ_ONLY,
    "get_edge_trigger_configuration": VerificationRisk.READ_ONLY,
    "configure_edge_trigger": VerificationRisk.REVERSIBLE,
    "set_trigger_level": VerificationRisk.REVERSIBLE,
    "set_edge_trigger_source": VerificationRisk.REVERSIBLE,
    "trigger": VerificationRisk.DISRUPTIVE,
    "force_trigger": VerificationRisk.DISRUPTIVE,
    "force_trigger_event": VerificationRisk.DISRUPTIVE,
    "rearm_trigger_after_image": VerificationRisk.DISRUPTIVE,
    "nudge_trigger_level_knob": VerificationRisk.DISRUPTIVE,
    "get_display_settings": VerificationRisk.READ_ONLY,
    "apply_display_settings": VerificationRisk.REVERSIBLE,
    "set_screen_message": VerificationRisk.REVERSIBLE,
    "clear_display_message": VerificationRisk.REVERSIBLE,
    "read_screen_png": VerificationRisk.READ_ONLY,
    "save_image_path": VerificationRisk.READ_ONLY,
    "save_scope_settings": VerificationRisk.READ_ONLY,
    "apply_scope_settings": VerificationRisk.DISRUPTIVE,
    "read_waveform": VerificationRisk.READ_ONLY,
    "read_channel_waveform_data": VerificationRisk.READ_ONLY,
    "read_enabled_waveforms": VerificationRisk.READ_ONLY,
    "save_waveform_to_csv": VerificationRisk.REVERSIBLE,
    "save_all_channels_to_csv": VerificationRisk.REVERSIBLE,
    "save_all_channels_to_single_csv": VerificationRisk.REVERSIBLE,
    "probe_reference_support": VerificationRisk.READ_ONLY,
    "get_reference_waveform_count": VerificationRisk.READ_ONLY,
    "get_available_reference_slots": VerificationRisk.READ_ONLY,
    "get_reference_configuration": VerificationRisk.READ_ONLY,
    "get_all_reference_configurations": VerificationRisk.READ_ONLY,
    "configure_reference": VerificationRisk.REVERSIBLE,
    "save_waveform_to_reference": VerificationRisk.DISRUPTIVE,
    "probe_bus_support": VerificationRisk.READ_ONLY,
    "get_bus_waveform_count": VerificationRisk.READ_ONLY,
    "get_available_bus_slots": VerificationRisk.READ_ONLY,
    "get_bus_configuration": VerificationRisk.READ_ONLY,
    "get_all_bus_configurations": VerificationRisk.READ_ONLY,
    "configure_bus": VerificationRisk.REVERSIBLE,
}

PUBLIC_FUNCTION_RISK: dict[str, VerificationRisk] = {
    "build_tcpip_instr_resource": VerificationRisk.READ_ONLY,
    "build_tcpip_socket_resource": VerificationRisk.READ_ONLY,
    "list_visa_resources": VerificationRisk.READ_ONLY,
    "scope_session": VerificationRisk.READ_ONLY,
    "extract_png_bytes": VerificationRisk.READ_ONLY,
    "strip_ieee_block_header": VerificationRisk.READ_ONLY,
    "parse_ascii_curve": VerificationRisk.READ_ONLY,
    "read_channel_waveform_data": VerificationRisk.READ_ONLY,
    "read_waveform": VerificationRisk.READ_ONLY,
}


def public_driver_methods() -> set[str]:
    """Return current public callable methods inherited by DPO4000Scope."""
    return {
        name
        for name, member in inspect.getmembers(DPO4000Scope, predicate=callable)
        if not name.startswith("_")
    }


def public_package_functions() -> set[str]:
    """Return functions exported by the package-level public API."""
    result: set[str] = set()
    for name in getattr(public_api, "__all__", ()):
        member = getattr(public_api, name, None)
        if inspect.isfunction(member):
            result.add(name)
    return result


def verification_manifest_gaps() -> dict[str, list[str]]:
    """Return public API symbols missing from the hardware-verification manifest."""
    return {
        "methods": sorted(public_driver_methods() - set(PUBLIC_METHOD_RISK)),
        "functions": sorted(public_package_functions() - set(PUBLIC_FUNCTION_RISK)),
    }


@dataclass
class VerificationConfig:
    resource: str
    output_dir: Path
    profile: VerificationRisk = VerificationRisk.READ_ONLY
    timeout_ms: int = 20_000
    test_channel: int = 1
    waveform_points: int = 1_000
    artifact_record_length: int = 1_000
    allow_reference_overwrite: bool = False
    reference_destination: int = 4


class HardwareVerifier:
    """Execute public-API verification cases against one connected oscilloscope."""

    def __init__(self, config: VerificationConfig):
        self.config = config
        self.config.output_dir = Path(self.config.output_dir)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[VerificationResult] = []
        self.scope: DPO4054 | None = None
        self.baseline_payload: dict[str, Any] | None = None
        self.idn = ""
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self._write_case_ran = False

    def _register_and_run(
        self,
        case: VerificationCase,
        callback: Callable[[], str | None],
    ) -> None:
        if case.risk > self.config.profile:
            self.results.append(
                VerificationResult(
                    case_id=case.case_id,
                    title=case.title,
                    risk=RISK_LABELS[case.risk],
                    status="SKIP",
                    duration_s=0.0,
                    covers_methods=list(case.covers_methods),
                    covers_functions=list(case.covers_functions),
                    detail=f"Profile {RISK_LABELS[self.config.profile]} does not enable this case.",
                )
            )
            return

        started = time.perf_counter()
        if case.risk >= VerificationRisk.REVERSIBLE:
            self._write_case_ran = True
        try:
            detail = callback() or ""
        except VerificationSkip as exc:
            result = VerificationResult(
                case_id=case.case_id,
                title=case.title,
                risk=RISK_LABELS[case.risk],
                status="SKIP",
                duration_s=time.perf_counter() - started,
                covers_methods=list(case.covers_methods),
                covers_functions=list(case.covers_functions),
                detail=str(exc),
            )
        except BaseException as exc:
            result = VerificationResult(
                case_id=case.case_id,
                title=case.title,
                risk=RISK_LABELS[case.risk],
                status="FAIL",
                duration_s=time.perf_counter() - started,
                covers_methods=list(case.covers_methods),
                covers_functions=list(case.covers_functions),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
        else:
            result = VerificationResult(
                case_id=case.case_id,
                title=case.title,
                risk=RISK_LABELS[case.risk],
                status="PASS",
                duration_s=time.perf_counter() - started,
                covers_methods=list(case.covers_methods),
                covers_functions=list(case.covers_functions),
                detail=detail,
            )
        self.results.append(result)

    def _require_scope(self) -> DPO4054:
        if self.scope is None:
            raise RuntimeError("Verification scope is not connected.")
        return self.scope

    def _capture_baseline(self) -> None:
        scope = self._require_scope()
        self.baseline_payload = build_scope_settings_payload(scope.ensure_connected())
        path = self.config.output_dir / "scope_setup_before.json"
        path.write_text(json.dumps(self.baseline_payload, indent=2), encoding="utf-8")

    def _restore_baseline(self) -> str:
        if not self.baseline_payload or self.scope is None:
            return "No baseline setup was captured."
        apply_setup_string(
            self.scope.ensure_connected(),
            self.baseline_payload["setup"],
            wait_complete=False,
            check_error=False,
            restore_delay_s=0.5,
        )
        after = build_scope_settings_payload(self.scope.ensure_connected())
        (self.config.output_dir / "scope_setup_after_restore.json").write_text(
            json.dumps(after, indent=2),
            encoding="utf-8",
        )
        return "Initial *LRN? setup reapplied and post-restore setup captured."

    def _case_manifest(self) -> str:
        gaps = verification_manifest_gaps()
        if gaps["methods"] or gaps["functions"]:
            raise AssertionError(
                "Hardware-verification manifest is incomplete: "
                f"methods={gaps['methods']}, functions={gaps['functions']}"
            )
        return (
            f"{len(PUBLIC_METHOD_RISK)} public driver methods and "
            f"{len(PUBLIC_FUNCTION_RISK)} package functions are classified."
        )

    def _case_pure_functions(self) -> str:
        assert public_api.build_tcpip_instr_resource("192.0.2.10") == "TCPIP0::192.0.2.10::INSTR"
        assert public_api.build_tcpip_socket_resource("192.0.2.10", 4000) == (
            "TCPIP0::192.0.2.10::4000::SOCKET"
        )
        block = b"#18" + b"\x89PNG\r\n\x1a\n"
        assert public_api.strip_ieee_block_header(block) == b"\x89PNG\r\n\x1a\n"
        assert public_api.extract_png_bytes(block).startswith(PNG_SIGNATURE)
        assert public_api.parse_ascii_curve("1,2.5,-3") == [1.0, 2.5, -3.0]
        return "Pure package helpers passed deterministic checks."

    def _case_lifecycle(self) -> str:
        resources = public_api.list_visa_resources()
        test_scope = DPO4054(
            self.config.resource,
            auto_connect=False,
            timeout_ms=self.config.timeout_ms,
            read_termination="\n",
            write_termination="\n",
        )
        test_scope.connect()
        try:
            instrument = test_scope.ensure_connected()
            original_timeout = getattr(instrument, "timeout", None)
            with test_scope.temporary_timeout(min(self.config.timeout_ms, 1_500)):
                assert test_scope.query_identity()
            assert getattr(instrument, "timeout", None) == original_timeout
        finally:
            test_scope.disconnect()

        with public_api.scope_session(
            self.config.resource,
            timeout_ms=self.config.timeout_ms,
        ) as session:
            idn = session.query_identity()
            assert idn

        if self.config.resource not in resources:
            visible = ", ".join(resources) if resources else "<none>"
            return (
                "Lifecycle/session checks passed. Target resource was not an exact "
                f"list_resources() match; visible resources: {visible}"
            )
        return "VISA discovery, connect/ensure/timeout/disconnect, and scope_session passed."

    def _case_identity_channels(self) -> str:
        scope = self._require_scope()
        self.idn = scope.query_identity().strip()
        label = scope.get_channel_label(self.config.test_channel)
        labels = scope.get_channel_labels()
        assert self.idn
        assert set(labels) == {1, 2, 3, 4}
        return f"IDN={self.idn}; CH{self.config.test_channel} label={label!r}."

    def _case_control_readbacks(self) -> str:
        scope = self._require_scope()
        scope.get_measurement_setup(1)
        setups = scope.get_all_measurement_setups()
        assert len(setups) == 8
        scope.read_measurement_value(1)
        scope.get_channel_configuration(self.config.test_channel)
        scope.get_math_configuration()
        scope.get_horizontal_position()
        scope.get_acquisition_setup()
        scope.get_acquisition_mode()
        scope.get_average_count()
        scope.get_record_length()
        scope.get_display_settings()
        return "Measurement/channel/MATH/horizontal/acquisition/display readback APIs passed."

    def _case_trigger_readbacks(self) -> str:
        scope = self._require_scope()
        scope.get_trigger_level(channel=self.config.test_channel)
        config = scope.get_edge_trigger_configuration()
        assert "source" in config
        return f"Edge trigger readback passed; source={config.get('source', '')}."

    def _case_reference_readbacks(self) -> str:
        scope = self._require_scope()
        count = scope.get_reference_waveform_count()
        slots = scope.get_available_reference_slots()
        assert len(slots) == count
        scope.get_all_reference_configurations()
        if not slots:
            raise VerificationSkip("Scope reports zero REF waveform slots.")
        scope.probe_reference_support(slots[0])
        scope.get_reference_configuration(slots[0])
        return f"REF capability/readback passed for slots {slots}."

    def _case_bus_readbacks(self) -> str:
        scope = self._require_scope()
        count = scope.get_bus_waveform_count()
        slots = scope.get_available_bus_slots()
        assert len(slots) == count
        scope.get_all_bus_configurations()
        if not slots:
            raise VerificationSkip(
                "Scope reports zero BUS waveform slots or option is unavailable."
            )
        scope.probe_bus_support(slots[0])
        config = scope.get_bus_configuration(slots[0])
        return (
            f"BUS capability/readback passed for slots {slots}; "
            f"BUS{slots[0]} type={config.get('type', '')}."
        )

    def _waveform_count(self) -> int:
        scope = self._require_scope()
        record_length = scope.get_record_length()
        return max(1, min(int(self.config.waveform_points), int(record_length)))

    def _case_waveform_readback(self) -> str:
        scope = self._require_scope()
        points = self._waveform_count()
        request = WaveformRequest(
            source=self.config.test_channel,
            start_index=1,
            point_count=points,
            encoding="RIBINARY",
            sample_width=2,
        )
        a = scope.read_waveform(request)
        b = scope.read_channel_waveform_data(self.config.test_channel, point_count=points)
        c = public_api.read_waveform(scope.ensure_connected(), request)
        d = public_api.read_channel_waveform_data(
            scope.ensure_connected(),
            self.config.test_channel,
            point_count=points,
        )
        enabled = scope.read_enabled_waveforms(point_count=points)
        assert a.sample_count == b.sample_count == c.sample_count == d.sample_count == points
        if not enabled:
            raise VerificationSkip(
                "No displayed analog channels are available for multi-channel waveform readback."
            )
        return f"Binary waveform APIs passed at {points} points; enabled sources={tuple(enabled)}."

    def _case_hardcopy(self) -> str:
        scope = self._require_scope()
        payload = scope.read_screen_png()
        assert payload.startswith(PNG_SIGNATURE)
        path = self.config.output_dir / "scope_screen.png"
        saved = scope.save_image_path(path)
        assert Path(saved).exists()
        return f"Hardcopy API passed; evidence={saved}."

    def _case_settings_save(self) -> str:
        scope = self._require_scope()
        path = self.config.output_dir / "scope_settings_driver_save.json"
        saved = scope.save_scope_settings(path, ask_before_overwrite=False)
        assert Path(saved).exists()
        return f"Settings save API passed; evidence={saved}."

    def _case_channel_write(self) -> str:
        scope = self._require_scope()
        channel = self.config.test_channel
        original = scope.get_channel_label(channel)
        sentinel = f"VERIFY_CH{channel}"[:30]
        try:
            scope.set_channel_label(channel, sentinel)
            assert scope.get_channel_label(channel) == sentinel
            config = scope.get_channel_configuration(channel)
            scope.configure_channel(
                ChannelConfig(
                    channel=channel,
                    display=bool_from_scope_response(config.get("display", "1")),
                    scale=config.get("scale") or None,
                    position=config.get("position") or None,
                )
            )
            scope.get_ch_max(channel)
        finally:
            scope.set_channel_label(channel, original)
        return "Channel label/configuration/immediate-MAX paths passed and label was restored."

    def _case_measurement_write(self) -> str:
        scope = self._require_scope()
        slot = 8
        scope.add_measurement(
            MeasurementConfig(
                slot=slot,
                measurement_type="MAXIMUM",
                source1=f"CH{self.config.test_channel}",
            )
        )
        configured = scope.get_measurement_setup(slot)
        assert configured.measurement_type
        scope.disable_measurement(slot)
        return "MEAS8 add/read/disable passed; baseline restore protects the original MEAS8 setup."

    def _case_math_horizontal_write(self) -> str:
        scope = self._require_scope()
        math = scope.get_math_configuration()
        scope.configure_math(MathConfig(display=bool_from_scope_response(math.get("display", "0"))))
        position = scope.get_horizontal_position()
        scope.set_horizontal_position(position)
        result = scope.nudge_horizontal_position(0)
        assert abs(result - position) < 1e-12
        return "MATH configuration and horizontal set/nudge passed without net horizontal change."

    def _case_acquisition_write(self) -> str:
        scope = self._require_scope()
        mode = scope.get_acquisition_mode()
        average = scope.get_average_count()
        record = scope.get_record_length()
        scope.configure_acquisition(
            AcquisitionConfig(mode=mode, average_count=average, record_length=record)
        )
        scope.set_acquisition_mode(mode)
        scope.set_average_count(average)
        scope.set_record_length(record)
        return f"Acquisition writes accepted current mode={mode}, avg={average}, record={record}."

    def _case_trigger_write(self) -> str:
        scope = self._require_scope()
        channel = self.config.test_channel
        current_level = scope.get_trigger_level(channel=channel)
        scope.configure_edge_trigger(
            source=f"CH{channel}",
            slope="RISE",
            coupling="DC",
            mode="AUTO",
            level=current_level,
        )
        scope.set_trigger_level(current_level, channel=channel, verify=True)
        scope.set_edge_trigger_source(channel)
        return (
            "Edge-trigger configure/level/source write paths passed on "
            f"CH{channel}; baseline restore protects the original trigger setup."
        )

    def _case_display_write(self) -> str:
        scope = self._require_scope()
        current = scope.get_display_settings()
        scope.apply_display_settings(
            DisplayConfig(message_state=bool_from_scope_response(current.get("message_state", "0")))
        )
        scope.set_screen_message("DPO4000 API VERIFY", state=True)
        scope.clear_display_message()
        return "Display apply/message/clear passed; baseline restore protects the original message."

    def _case_reference_write(self) -> str:
        scope = self._require_scope()
        slots = scope.get_available_reference_slots()
        if not slots:
            raise VerificationSkip("No REF slots available.")
        slot = slots[0]
        current = scope.get_reference_configuration(slot)
        scope.configure_reference(
            ReferenceConfig(
                reference=slot,
                display=bool_from_scope_response(current.get("display", "0")),
                label=current.get("label") or None,
                vertical_scale=current.get("vertical_scale") or None,
                vertical_position=current.get("vertical_position") or None,
            )
        )
        return f"REF{slot} configure path passed using its current values."

    def _case_bus_write(self) -> str:
        scope = self._require_scope()
        slots = scope.get_available_bus_slots()
        if not slots:
            raise VerificationSkip("No BUS slots available or serial-bus option is not licensed.")
        slot = slots[0]
        current = scope.get_bus_configuration(slot)
        scope.configure_bus(
            BusConfig(
                bus=slot,
                state=bool_from_scope_response(current.get("state", "0")),
                bus_type=current.get("type") or None,
                label=current.get("label") or None,
                position=current.get("position") or None,
                display_format=current.get("display_format") or None,
                display_type=current.get("display_type") or None,
            )
        )
        return f"BUS{slot} configure path passed using current common settings."

    def _case_legacy_csv(self) -> str:
        scope = self._require_scope()
        original_record = scope.get_record_length()
        target = min(original_record, max(1_000, int(self.config.artifact_record_length)))
        try:
            if target != original_record:
                scope.set_record_length(target)
            current_display = scope.get_channel_configuration(self.config.test_channel).get(
                "display", "0"
            )
            if not bool_from_scope_response(current_display):
                scope.configure_channel(
                    ChannelConfig(channel=self.config.test_channel, display=True)
                )
            single = scope.save_waveform_to_csv(
                self.config.test_channel,
                self.config.output_dir / f"CH{self.config.test_channel}_legacy.csv",
            )
            separate = scope.save_all_channels_to_csv(
                self.config.output_dir / "all_channels_legacy"
            )
            combined = scope.save_all_channels_to_single_csv(
                self.config.output_dir / "all_channels_combined.csv"
            )
            assert Path(single).exists()
            assert separate
            assert Path(combined).exists()
        finally:
            if target != original_record:
                scope.set_record_length(original_record)
        return f"Legacy CSV methods passed at temporary record length {target}."

    def _case_settings_apply(self) -> str:
        scope = self._require_scope()
        path = self.config.output_dir / "scope_settings_driver_save.json"
        if not path.exists():
            scope.save_scope_settings(path, ask_before_overwrite=False)
        scope.apply_scope_settings(
            path,
            wait_complete=False,
            check_error=False,
            restore_delay_s=0.5,
        )
        return "Driver settings apply method accepted and reapplied the captured setup file."

    def _case_acquisition_trigger_disruptive(self) -> str:
        scope = self._require_scope()
        scope.disable_all_measurements()
        scope.stop_acquisition()
        scope.run_acquisition()
        scope.single_acquisition()
        scope.continuous_acquisition()
        scope.trigger()
        scope.force_trigger()
        scope.force_trigger_event()
        scope.rearm_trigger_after_image(
            trigger_channel=self.config.test_channel,
            restore_level=True,
        )
        scope.nudge_trigger_level_knob()
        return (
            "Disruptive acquisition/trigger methods executed; baseline restore will recover setup."
        )

    def _case_reference_store(self) -> str:
        scope = self._require_scope()
        if not self.config.allow_reference_overwrite:
            raise VerificationSkip(
                "REF waveform overwrite not authorized. Re-run with --allow-reference-overwrite "
                "and choose a disposable reference slot to exercise save_waveform_to_reference()."
            )
        slots = scope.get_available_reference_slots()
        if self.config.reference_destination not in slots:
            raise VerificationSkip(
                f"Requested REF{self.config.reference_destination} "
                f"is unavailable; available={slots}."
            )
        scope.save_waveform_to_reference(
            f"CH{self.config.test_channel}",
            self.config.reference_destination,
        )
        return (
            f"Stored CH{self.config.test_channel} into REF{self.config.reference_destination}. "
            "This changes reference waveform contents and "
            "is intentionally not treated as reversible."
        )

    def run(self) -> dict[str, Any]:
        self._register_and_run(
            VerificationCase(
                "manifest", "Public API manifest completeness", VerificationRisk.READ_ONLY
            ),
            self._case_manifest,
        )
        self._register_and_run(
            VerificationCase(
                "pure-functions",
                "Pure package helper functions",
                VerificationRisk.READ_ONLY,
                covers_functions=(
                    "build_tcpip_instr_resource",
                    "build_tcpip_socket_resource",
                    "extract_png_bytes",
                    "strip_ieee_block_header",
                    "parse_ascii_curve",
                ),
            ),
            self._case_pure_functions,
        )
        self._register_and_run(
            VerificationCase(
                "lifecycle",
                "VISA discovery and session lifecycle",
                VerificationRisk.READ_ONLY,
                covers_methods=(
                    "connect",
                    "disconnect",
                    "ensure_connected",
                    "temporary_timeout",
                    "query_identity",
                ),
                covers_functions=("list_visa_resources", "scope_session"),
            ),
            self._case_lifecycle,
        )

        self.scope = DPO4054(
            self.config.resource,
            auto_connect=False,
            timeout_ms=self.config.timeout_ms,
            read_termination="\n",
            write_termination="\n",
        )
        try:
            self.scope.connect()
            self.idn = self.scope.query_identity().strip()
            self._capture_baseline()

            cases: list[tuple[VerificationCase, Callable[[], str | None]]] = [
                (
                    VerificationCase(
                        "identity-channels",
                        "Identity and channel readback",
                        VerificationRisk.READ_ONLY,
                        covers_methods=(
                            "query_identity",
                            "get_channel_label",
                            "get_channel_labels",
                        ),
                    ),
                    self._case_identity_channels,
                ),
                (
                    VerificationCase(
                        "control-readbacks",
                        "Control-plane readback API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=(
                            "get_measurement_setup",
                            "get_all_measurement_setups",
                            "read_measurement_value",
                            "get_channel_configuration",
                            "get_math_configuration",
                            "get_horizontal_position",
                            "get_acquisition_setup",
                            "get_acquisition_mode",
                            "get_average_count",
                            "get_record_length",
                            "get_display_settings",
                        ),
                    ),
                    self._case_control_readbacks,
                ),
                (
                    VerificationCase(
                        "trigger-readbacks",
                        "Trigger readback API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=("get_trigger_level", "get_edge_trigger_configuration"),
                    ),
                    self._case_trigger_readbacks,
                ),
                (
                    VerificationCase(
                        "reference-readbacks",
                        "Reference waveform capability/readback API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=(
                            "probe_reference_support",
                            "get_reference_waveform_count",
                            "get_available_reference_slots",
                            "get_reference_configuration",
                            "get_all_reference_configurations",
                        ),
                    ),
                    self._case_reference_readbacks,
                ),
                (
                    VerificationCase(
                        "bus-readbacks",
                        "BUS capability/readback API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=(
                            "probe_bus_support",
                            "get_bus_waveform_count",
                            "get_available_bus_slots",
                            "get_bus_configuration",
                            "get_all_bus_configurations",
                        ),
                    ),
                    self._case_bus_readbacks,
                ),
                (
                    VerificationCase(
                        "waveform-readback",
                        "Structured binary waveform API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=(
                            "read_waveform",
                            "read_channel_waveform_data",
                            "read_enabled_waveforms",
                        ),
                        covers_functions=("read_waveform", "read_channel_waveform_data"),
                    ),
                    self._case_waveform_readback,
                ),
                (
                    VerificationCase(
                        "hardcopy",
                        "Screen hardcopy API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=("read_screen_png", "save_image_path"),
                    ),
                    self._case_hardcopy,
                ),
                (
                    VerificationCase(
                        "settings-save",
                        "Settings save API",
                        VerificationRisk.READ_ONLY,
                        covers_methods=("save_scope_settings",),
                    ),
                    self._case_settings_save,
                ),
                (
                    VerificationCase(
                        "channel-write",
                        "Reversible channel write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=("set_channel_label", "configure_channel", "get_ch_max"),
                    ),
                    self._case_channel_write,
                ),
                (
                    VerificationCase(
                        "measurement-write",
                        "Measurement write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=("add_measurement", "disable_measurement"),
                    ),
                    self._case_measurement_write,
                ),
                (
                    VerificationCase(
                        "math-horizontal-write",
                        "MATH and horizontal write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=(
                            "configure_math",
                            "set_horizontal_position",
                            "nudge_horizontal_position",
                        ),
                    ),
                    self._case_math_horizontal_write,
                ),
                (
                    VerificationCase(
                        "acquisition-write",
                        "Acquisition configuration write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=(
                            "configure_acquisition",
                            "set_acquisition_mode",
                            "set_average_count",
                            "set_record_length",
                        ),
                    ),
                    self._case_acquisition_write,
                ),
                (
                    VerificationCase(
                        "trigger-write",
                        "Reversible edge-trigger write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=(
                            "configure_edge_trigger",
                            "set_trigger_level",
                            "set_edge_trigger_source",
                        ),
                    ),
                    self._case_trigger_write,
                ),
                (
                    VerificationCase(
                        "display-write",
                        "Display/message write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=(
                            "apply_display_settings",
                            "set_screen_message",
                            "clear_display_message",
                        ),
                    ),
                    self._case_display_write,
                ),
                (
                    VerificationCase(
                        "reference-write",
                        "Reference display configuration write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=("configure_reference",),
                    ),
                    self._case_reference_write,
                ),
                (
                    VerificationCase(
                        "bus-write",
                        "BUS configuration write API",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=("configure_bus",),
                    ),
                    self._case_bus_write,
                ),
                (
                    VerificationCase(
                        "legacy-csv",
                        "Legacy waveform CSV compatibility methods",
                        VerificationRisk.REVERSIBLE,
                        covers_methods=(
                            "save_waveform_to_csv",
                            "save_all_channels_to_csv",
                            "save_all_channels_to_single_csv",
                        ),
                    ),
                    self._case_legacy_csv,
                ),
                (
                    VerificationCase(
                        "settings-apply",
                        "Settings restore API",
                        VerificationRisk.DISRUPTIVE,
                        covers_methods=("apply_scope_settings",),
                    ),
                    self._case_settings_apply,
                ),
                (
                    VerificationCase(
                        "acquisition-trigger-disruptive",
                        "Acquisition/trigger disruptive API",
                        VerificationRisk.DISRUPTIVE,
                        covers_methods=(
                            "disable_all_measurements",
                            "run_acquisition",
                            "stop_acquisition",
                            "single_acquisition",
                            "continuous_acquisition",
                            "trigger",
                            "force_trigger",
                            "force_trigger_event",
                            "rearm_trigger_after_image",
                            "nudge_trigger_level_knob",
                        ),
                    ),
                    self._case_acquisition_trigger_disruptive,
                ),
                (
                    VerificationCase(
                        "reference-store",
                        "Reference waveform storage API",
                        VerificationRisk.DISRUPTIVE,
                        covers_methods=("save_waveform_to_reference",),
                    ),
                    self._case_reference_store,
                ),
            ]
            for case, callback in cases:
                self._register_and_run(case, callback)
        except BaseException as exc:
            self.results.append(
                VerificationResult(
                    case_id="session-fatal",
                    title="Verification session",
                    risk="read-only",
                    status="FAIL",
                    duration_s=0.0,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
            )
        finally:
            if self.scope is not None:
                if self._write_case_ran and self.baseline_payload is not None:
                    self._register_and_run(
                        VerificationCase(
                            "baseline-restore",
                            "Restore initial scope setup",
                            VerificationRisk.READ_ONLY,
                        ),
                        self._restore_baseline,
                    )
                try:
                    self.scope.disconnect()
                except BaseException as exc:
                    self.results.append(
                        VerificationResult(
                            case_id="disconnect-final",
                            title="Final VISA disconnect",
                            risk="read-only",
                            status="FAIL",
                            duration_s=0.0,
                            error_type=exc.__class__.__name__,
                            error_message=str(exc),
                        )
                    )

        self.finished_at = datetime.now(timezone.utc)
        report = self.build_report()
        self.write_report_files(report)
        return report

    def _symbol_status(self, symbol: str, *, method: bool) -> tuple[str, list[str]]:
        matching = [
            result
            for result in self.results
            if symbol in (result.covers_methods if method else result.covers_functions)
        ]
        if not matching:
            return "UNVERIFIED", []
        statuses = {result.status for result in matching}
        if "FAIL" in statuses:
            status = "FAIL"
        elif "PASS" in statuses:
            status = "PASS"
        else:
            status = "SKIP"
        return status, [result.case_id for result in matching]

    def build_report(self) -> dict[str, Any]:
        try:
            package_version = metadata.version("dpo4000-utils")
        except metadata.PackageNotFoundError:
            package_version = "source-tree"

        methods = []
        for name in sorted(PUBLIC_METHOD_RISK):
            status, cases = self._symbol_status(name, method=True)
            methods.append(
                {
                    "symbol": name,
                    "risk": RISK_LABELS[PUBLIC_METHOD_RISK[name]],
                    "status": status,
                    "cases": cases,
                }
            )
        functions = []
        for name in sorted(PUBLIC_FUNCTION_RISK):
            status, cases = self._symbol_status(name, method=False)
            functions.append(
                {
                    "symbol": name,
                    "risk": RISK_LABELS[PUBLIC_FUNCTION_RISK[name]],
                    "status": status,
                    "cases": cases,
                }
            )

        totals = {
            status: sum(1 for result in self.results if result.status == status)
            for status in ("PASS", "FAIL", "SKIP")
        }
        api_totals = {
            "methods_pass": sum(1 for item in methods if item["status"] == "PASS"),
            "methods_total": len(methods),
            "functions_pass": sum(1 for item in functions if item["status"] == "PASS"),
            "functions_total": len(functions),
            "unverified": sum(
                1 for item in [*methods, *functions] if item["status"] == "UNVERIFIED"
            ),
        }
        return {
            "schema_version": 1,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else "",
            "package_version": package_version,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "resource": self.config.resource,
            "idn": self.idn,
            "profile": RISK_LABELS[self.config.profile],
            "test_channel": self.config.test_channel,
            "waveform_points": self.config.waveform_points,
            "allow_reference_overwrite": self.config.allow_reference_overwrite,
            "reference_destination": self.config.reference_destination,
            "totals": totals,
            "api_totals": api_totals,
            "results": [asdict(result) for result in self.results],
            "methods": methods,
            "functions": functions,
        }

    def write_report_files(self, report: dict[str, Any]) -> None:
        (self.config.output_dir / "verification_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        (self.config.output_dir / "verification_report.md").write_text(
            self._render_markdown(report), encoding="utf-8"
        )
        (self.config.output_dir / "verification_report.html").write_text(
            self._render_html(report), encoding="utf-8"
        )

    @staticmethod
    def _render_markdown(report: dict[str, Any]) -> str:
        api = report["api_totals"]
        lines = [
            "# DPO4000 Real-Hardware Verification Report",
            "",
            f"- Package: `{report['package_version']}`",
            f"- Resource: `{report['resource']}`",
            f"- Instrument: `{report['idn'] or 'unknown'}`",
            f"- Profile: **{report['profile']}**",
            f"- Started: `{report['started_at']}`",
            f"- Finished: `{report['finished_at']}`",
            "",
            "## Summary",
            "",
            f"- PASS cases: **{report['totals']['PASS']}**",
            f"- FAIL cases: **{report['totals']['FAIL']}**",
            f"- SKIP cases: **{report['totals']['SKIP']}**",
            f"- Driver methods passed: **{api['methods_pass']}/{api['methods_total']}**",
            f"- Package functions passed: **{api['functions_pass']}/{api['functions_total']}**",
            f"- Unverified public symbols: **{api['unverified']}**",
            "",
            "## Verification cases",
            "",
            "| Case | Risk | Status | Duration (s) | Detail |",
            "| --- | --- | --- | ---: | --- |",
        ]
        for result in report["results"]:
            detail = (
                (result["detail"] or result["error_message"]).replace("|", "\\|").replace("\n", " ")
            )
            lines.append(
                f"| `{result['case_id']}` | {result['risk']} | **{result['status']}** | "
                f"{result['duration_s']:.3f} | {detail} |"
            )
        lines.extend(
            [
                "",
                "## Public driver method coverage",
                "",
                "| Method | Risk | Status | Cases |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in report["methods"]:
            lines.append(
                f"| `{item['symbol']}` | {item['risk']} | **{item['status']}** | "
                f"{', '.join(item['cases']) or '-'} |"
            )
        lines.extend(
            [
                "",
                "## Package-level public function coverage",
                "",
                "| Function | Risk | Status | Cases |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in report["functions"]:
            lines.append(
                f"| `{item['symbol']}` | {item['risk']} | **{item['status']}** | "
                f"{', '.join(item['cases']) or '-'} |"
            )
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_html(report: dict[str, Any]) -> str:
        def table_rows(items: list[dict[str, Any]], symbol_key: str) -> str:
            rows = []
            for item in items:
                rows.append(
                    "<tr>"
                    f"<td><code>{html.escape(str(item[symbol_key]))}</code></td>"
                    f"<td>{html.escape(str(item['risk']))}</td>"
                    f"<td><strong>{html.escape(str(item['status']))}</strong></td>"
                    f"<td>{html.escape(', '.join(item.get('cases', [])) or '-')}</td>"
                    "</tr>"
                )
            return "\n".join(rows)

        case_rows = []
        for item in report["results"]:
            detail = item["detail"] or item["error_message"]
            case_rows.append(
                "<tr>"
                f"<td><code>{html.escape(item['case_id'])}</code></td>"
                f"<td>{html.escape(item['risk'])}</td>"
                f"<td><strong>{html.escape(item['status'])}</strong></td>"
                f"<td>{item['duration_s']:.3f}</td>"
                f"<td>{html.escape(detail)}</td>"
                "</tr>"
            )
        return f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>DPO4000 hardware verification</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
th,td{{border:1px solid #bbb;padding:.4rem;text-align:left;vertical-align:top}}
code{{white-space:nowrap}}
</style></head><body>
<h1>DPO4000 Real-Hardware Verification Report</h1>
<p><b>Package:</b> {html.escape(str(report["package_version"]))}<br>
<b>Resource:</b> {html.escape(str(report["resource"]))}<br>
<b>Instrument:</b> {html.escape(str(report["idn"] or "unknown"))}<br>
<b>Profile:</b> {html.escape(str(report["profile"]))}</p>
<h2>Summary</h2>
<p>PASS {report["totals"]["PASS"]} / FAIL {report["totals"]["FAIL"]} /
SKIP {report["totals"]["SKIP"]}<br>
Methods {report["api_totals"]["methods_pass"]}/{report["api_totals"]["methods_total"]} passed;
functions {report["api_totals"]["functions_pass"]}/{report["api_totals"]["functions_total"]} passed;
unverified {report["api_totals"]["unverified"]}.</p>
<h2>Verification cases</h2>
<table><tr><th>Case</th><th>Risk</th><th>Status</th><th>s</th><th>Detail</th></tr>
{"".join(case_rows)}</table>
<h2>Public driver methods</h2>
<table><tr><th>Method</th><th>Risk</th><th>Status</th><th>Cases</th></tr>
{table_rows(report["methods"], "symbol")}</table>
<h2>Package functions</h2>
<table><tr><th>Function</th><th>Risk</th><th>Status</th><th>Cases</th></tr>
{table_rows(report["functions"], "symbol")}</table>
</body></html>"""

    def exit_code(self, report: dict[str, Any]) -> int:
        if report["totals"]["FAIL"] or report["api_totals"]["unverified"]:
            return 1
        if self.config.profile == VerificationRisk.DISRUPTIVE:
            ref_store = next(
                (
                    item
                    for item in report["methods"]
                    if item["symbol"] == "save_waveform_to_reference"
                ),
                None,
            )
            if ref_store is not None and ref_store["status"] != "PASS":
                return 2
        return 0


__all__ = [
    "HardwareVerifier",
    "PUBLIC_FUNCTION_RISK",
    "PUBLIC_METHOD_RISK",
    "VerificationCase",
    "VerificationConfig",
    "VerificationResult",
    "VerificationRisk",
    "public_driver_methods",
    "public_package_functions",
    "verification_manifest_gaps",
]
