"""Logger L7 synchronized mixed-record mode."""
from __future__ import annotations
from threading import Event
from ..logger.models import LoggerConfig, LoggerMode, LoggerRecord, LoggerState
from ..logger.producer import LoggerCaptureCancelled, capture_logger_record
from .logger_bus_window import QtScopeWindow as LoggerL6QtScopeWindow

class QtScopeWindow(LoggerL6QtScopeWindow):
    def __init__(self, *args, **kwargs) -> None:
        self._logger_capture_cancel: Event | None = None
        super().__init__(*args, **kwargs)

    def _build_logger_sources_card(self):
        card = super()._build_logger_sources_card()
        if self.logger_mode_combo.findText(LoggerMode.MIXED.value) < 0: self.logger_mode_combo.addItem(LoggerMode.MIXED.value)
        return card

    def _logger_mode_changed(self, *_args) -> None:
        super()._logger_mode_changed(*_args)
        mixed = self._logger_mode() is LoggerMode.MIXED
        measurement_row = getattr(self, "logger_measurement_row", None)
        bus_row = getattr(self, "logger_bus_row", None)
        if measurement_row is not None: measurement_row.setVisible(mixed or self._logger_mode() is LoggerMode.MEASUREMENTS)
        if bus_row is not None: bus_row.setVisible(mixed or self._logger_mode() is LoggerMode.BUS)

    def _logger_config(self) -> LoggerConfig:
        if self._logger_mode() is LoggerMode.MIXED:
            return LoggerConfig(
                mode=LoggerMode.MIXED,
                interval_s=float(self.logger_interval.value()),
                waveform_sources=self._logger_selected_sources(),
                measurement_slots=self._logger_selected_measurements(),
                bus_slots=self._logger_selected_buses(),
            )
        return super()._logger_config()

    def start_logger(self) -> None:
        if self._logger_mode() is LoggerMode.MIXED:
            try: config = self._logger_config()
            except Exception as exc:
                self._message("Logger", str(exc), error=True); return
            if config.bus_slots:
                supported = self._run_action("Checking decoded BUS logger capability", lambda scope: bool(scope.supports_decoded_bus_events()))
                if supported is not True:
                    self._message("Logger BUS", "Mixed logging requested BUS events, but decoded BUS extraction is not hardware-qualified for this driver/scope.", error=True); return
        super().start_logger()

    def stop_logger(self) -> None:
        cancel = self._logger_capture_cancel
        if cancel is not None: cancel.set()
        super().stop_logger()

    def _logger_tick(self) -> None:
        if self._logger_mode() is not LoggerMode.MIXED:
            super()._logger_tick(); return
        if self._logger_state is not LoggerState.RUNNING: return
        if self._logger_busy:
            self._logger_statistics.skipped += 1; self._logger_refresh_status(); return
        config = self._logger_config_active; output = self._logger_output_session
        if config is None or output is None: return
        self._logger_busy = True; self._logger_sequence += 1; sequence = self._logger_sequence
        cancel = Event(); self._logger_capture_cancel = cancel
        try:
            result = self._run_action(f"Logger synchronized capture #{sequence:08d}", lambda scope: capture_logger_record(scope, config, sequence, cancel_event=cancel))
            if not isinstance(result, LoggerRecord): raise RuntimeError(str(getattr(self, "_last_action", "Logger mixed capture failed")))
            self._logger_statistics.records_captured += 1
            output.append(result); self._logger_statistics.records_written = output.records_written; self._logger_statistics.bytes_written = output.bytes_written
            self._logger_statistics.last_error = ""; self._logger_last_file = output.paths[-1] if output.paths else None
            if result.metadata.get("partial"): self._append_log(f"Logger mixed record {sequence} written as PARTIAL: {result.metadata}")
            self.statusBar().showMessage(f"Mixed Logger record {sequence} written")
        except LoggerCaptureCancelled:
            self._logger_statistics.skipped += 1
        except Exception as exc:
            self._logger_statistics.failed += 1; self._logger_statistics.last_error = str(exc); self._logger_state = LoggerState.FAILED
            timer = self._logger_timer
            if timer is not None: timer.stop()
            try: output.close()
            except Exception as close_exc: self._append_log(f"Logger output close after failure also failed: {close_exc}")
            self._logger_output_session = None; self._append_log(f"Logger L7 failed: {exc}")
        finally:
            self._logger_capture_cancel = None; self._logger_busy = False; self._logger_refresh_status()

__all__ = ["QtScopeWindow"]
