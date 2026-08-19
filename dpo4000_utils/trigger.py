"""Acquisition and trigger helpers."""

from __future__ import annotations

import time

from .channels import validate_channel


class TriggerMixin:
    """Mixin for acquisition and A trigger helpers."""

    def trigger(self):
        """Initiate a single acquisition trigger on the oscilloscope."""
        self.ensure_connected().write("ACQUIRE:STATE ON")

    def force_trigger(self):
        """Force a trigger event on the oscilloscope."""
        self.ensure_connected().write("TRIG FORC")

    def set_trigger_level(self, level, channel=None, verify=True):
        """
        Set A trigger level.

        ``level`` may be a numeric voltage or the strings ``TTL`` / ``ECL``.
        """
        scope = self.ensure_connected()

        if isinstance(level, str):
            level_value = level.strip().upper()
            if level_value not in ("TTL", "ECL"):
                raise ValueError("String level must be 'TTL' or 'ECL'.")
        else:
            level_value = float(level)

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

    def set_edge_trigger_source(self, channel):
        """Set A edge trigger source to CH1..CH4."""
        validate_channel(channel)
        self.ensure_connected().write(f"TRIGGER:A:EDGE:SOURCE CH{channel}")

    def rearm_trigger_after_image(self, trigger_channel=None, restore_level=True):
        """Re-arm trigger/acquisition after screen image read."""
        scope = self.ensure_connected()
        time.sleep(0.3)

        try:
            scope.write("*CLS")
        except Exception:
            pass

        try:
            trig_mode = scope.query("TRIGGER:A:MODE?").strip().split()[-1]
            scope.write(f"TRIGGER:A:MODE {trig_mode}")
        except Exception:
            pass

        if restore_level:
            try:
                if trigger_channel is None:
                    level = scope.query("TRIGGER:A:LEVEL?").strip().split()[-1]
                    scope.write(f"TRIGGER:A:LEVEL {level}")
                else:
                    validate_channel(trigger_channel)
                    level = scope.query(
                        f"TRIGGER:A:LEVEL:CH{trigger_channel}?"
                    ).strip().split()[-1]
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
