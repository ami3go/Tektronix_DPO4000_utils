"""Save current oscilloscope settings to JSON."""

from dpo4000_utils import DPO4054


scope = DPO4054(auto_connect=True)
try:
    saved_path = scope.save_scope_settings("scope_setup.json", ask_before_overwrite=False)
    print(saved_path)
finally:
    scope.disconnect()
