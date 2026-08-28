"""Channel label and simple measurement helpers."""

from __future__ import annotations

from .scpi_values import quote_scpi_string


def validate_channel(channel: int) -> None:
    if channel < 1 or channel > 4:
        raise ValueError("Channel must be between 1 and 4.")


class ChannelMixin:
    """Mixin for channel labels and simple channel measurements."""

    def set_channel_label(self, channel, label):
        """Set a safely quoted label for a specific channel."""
        validate_channel(channel)
        clean_label = str(label)[:30]
        self.channel_labels[channel] = clean_label
        self.ensure_connected().write(
            f"CH{channel}:LABEL {quote_scpi_string(clean_label, max_length=30)}"
        )

    def get_channel_label(self, channel):
        """Read label from a specific oscilloscope channel."""
        validate_channel(channel)
        response = self.ensure_connected().query(f"CH{channel}:LABEL?").strip()

        if "\"" in response:
            label = response.split("\"", 1)[1].rsplit("\"", 1)[0]
        else:
            label = response.replace(f":CH{channel}:LABEL", "").strip()

        self.channel_labels[channel] = label
        return label

    def get_channel_labels(self):
        """Read all CH1..CH4 labels."""
        return {channel: self.get_channel_label(channel) for channel in range(1, 5)}

    def get_ch_max(self, ch_num):
        """Return immediate maximum measurement for the given channel."""
        validate_channel(ch_num)
        scope = self.ensure_connected()
        scope.write("MEASUrement:IMMed:TYPe MAXimum")
        scope.write(f"MEASUrement:IMMed:SOUrce CH{ch_num}")
        return scope.query("MEASUrement:IMMed:VALue?")
