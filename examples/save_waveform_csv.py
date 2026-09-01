"""Save enabled channels to one CSV file."""

from dpo4000_utils import DPO4054

scope = DPO4054(auto_connect=True)
try:
    scope.save_all_channels_to_single_csv("waveform_enabled_channels.csv")
finally:
    scope.disconnect()
