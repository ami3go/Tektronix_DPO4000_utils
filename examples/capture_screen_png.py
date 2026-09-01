"""Capture the current oscilloscope screen to a PNG file."""

from dpo4000_utils import DPO4054

scope = DPO4054(auto_connect=True)
try:
    scope.save_image_path("scope_screen.png")
finally:
    scope.disconnect()
