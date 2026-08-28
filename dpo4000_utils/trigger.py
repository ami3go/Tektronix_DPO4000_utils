"""Acquisition and trigger helpers."""

from __future__ import annotations

import time

from .channels import validate_channel
from .scpi_values import ensure_single_scpi_value, format_scpi_number


class TriggerMixin:
    """Mixin for acquisition and A trigger helpers."""

    @staticmethod
    def _query_value(scope, command: str) -> str:
        """Return the useful value token from a Tektronix query response."""
        response = scope.query(command).strip()
        if '"' in response:
            return response.split('"', 1)[1].rsplit('"', 1)[0]
        parts = response.split()
        return parts[-1] if parts else ""

    def trigger(self):
        """Initiate a single acquisition trigger on the oscilloscope."""
        self.ensure_connected().write("ACQUIRE:STATE ON")

    def force_trigger(self):
        """Force a trigger event on the oscilloscope."""
        self.ensure_connected().write("TRIG FORC")

    def set_trigger_level(self, level, channel=None, verify=True):
        """Set A trigger level using a finite numeric value, TTL, or ECL."""
        scope = self.ensure_connected()
        text = ensure_single_scpi_value(level, field="Trigger level")
        preset = text.upper()
        level_value = preset if preset in {"TTL", "ECL"} else format_scpi_number(
            text,
            field="Trigger level",
        )

        if channel is None:
            command = "TRIGGER:A:LEVEL"
        else:
            validate_channel(channel)
            command = f"TRIGGER:A:LEVEL:CH{channel}"

        scope.write(f"{command} {level_value}")

        if verify:
            return self.get_trigger_level(channel=channel)
        return None

    def get_trigger_level(self, channel=None):
        """Read A trigger level."""
        scope = self.ensure_connected()

        if channel is None:
            command = "TRIGGER:A:LEVEL?"
        else:
            validate_channel(channel)
            command = f"TRIGGER:A:LEVEL:CH{channel}?"

        response = scope.query(command).strip()
        value_text = response.split()[-1]

        try:
            return float(value_text)
        except ValueError:
            return response

    def get_edge_trigger_configuration(self) -> dict[str, str]:
        """Read the A edge-trigger fields used by DPO4000 Desk."""
        scope = self.ensure_connected()
        source = self._query_value(scope, "TRIGGER:A:EDGE:SOURCE?").upper()
        level_query = (
            f"TRIGGER:A:LEVEL:{source}?"
            if source.startswith("CH") and source[2:].isdigit()
            else "TRIGGER:A:LEVEL?"
        )
        return {
            "mode": self._query_value(scope, "TRIGGER:A:MODE?").upper(),
            "source": source,
            "slope": self._query_value(scope, "TRIGGER:A:EDGE:SLOPE?").upper(),
            "coupling": self._query_value(scope, "TRIGGER:A:EDGE:COUPLING?").upper(),
            "level": self._query_value(scope, level_query),
        }

    def set_edge_trigger_source(self, channel):
        """Set A edge trigger source to CH1..CH4."""
        validate_channel(channel)
        self.ensure_connected().write(f"TRIGGER:A:EDGE:SOURCE CH{channel}")

    def rearm_trigger_after_image(self, trigger_channel=None, restore_level=True):
        """Re-arm acquisition after image read without clearing instrument status.

        Legacy firmware sometimes benefited from re-writing trigger mode/level after
        hardcopy. Those values are validated before being written back. ``*CLS`` is
        deliberately not used so image capture/rearm cannot erase diagnostic state.
        """
        scope = self.ensure_connected()
        time.sleep(0.3)

        try:
            trig_mode = ensure_single_scpi_value(
                scope.query("TRIGGER:A:MODE?").strip().split()[-1],
                field="Trigger mode readback",
            )
            scope.write(f"TRIGGER:A:MODE {trig_mode}")
        except Exception:
            pass

        if restore_level:
            try:
                if trigger_channel is None:
                    level = format_scpi_number(
                        scope.query("TRIGGER:A:LEVEL?").strip().split()[-1],
                        field="Trigger level readback",
                    )
                    scope.write(f"TRIGGER:A:LEVEL {level}")
                else:
                    validate_channel(trigger_channel)
                    level = format_scpi_number(
                        scope.query(
                            f"TRIGGER:A:LEVEL:CH{trigger_channel}?"
                        ).strip().split()[-1],
                        field="Trigger level readback",
                    )
                    scope.write(f"TRIGGER:A:LEVEL:CH{trigger_channel} {level}")
            except Exception:
                pass

        scope.write("ACQUIRE:STATE RUN")
        time.sleep(0.2)

    def nudge_trigger_level_knob(self):
        """Simulate moving trigger level knob up and back, then run acquisition."""
        scope = self.ensure_connected()
        scope.write("FPANEL:TURN TRIGLEVEL,1")
        time.sleep(0.1)
        scope.write("FPANEL:TURN TRIGLEVEL,-1")
        time.sleep(0.2)
        scope.write("ACQUIRE:STATE RUN")
