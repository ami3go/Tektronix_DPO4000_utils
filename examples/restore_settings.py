"""Restore oscilloscope settings from JSON if the driver exposes apply_scope_settings."""

from dpo4000_utils import DPO4054


scope = DPO4054(auto_connect=True)
try:
    if not hasattr(scope, "apply_scope_settings"):
        raise RuntimeError("This driver version does not expose apply_scope_settings(). Use the GUI restore flow.")
    scope.apply_scope_settings("scope_setup.json", wait_complete=False)
finally:
    scope.disconnect()
