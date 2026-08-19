"""Read and write channel labels."""

from dpo4000_utils import DPO4054


scope = DPO4054(auto_connect=True)
try:
    for channel in range(1, 5):
        print(f"CH{channel}: {scope.get_channel_label(channel)!r}")

    scope.set_channel_label(1, "INPUT")
finally:
    scope.disconnect()
