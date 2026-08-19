"""Project-specific exceptions for DPO4000 utilities."""


class DPOError(Exception):
    """Base exception for DPO4000 utility errors."""


class DPOConnectionError(ConnectionError, DPOError):
    """Raised when the oscilloscope cannot be connected or used."""


class DPONotConnectedError(DPOConnectionError):
    """Raised when an operation requires an open oscilloscope session."""


class DPOImageCaptureError(DPOError):
    """Raised when screen hardcopy data cannot be captured or parsed."""


class DPOSettingsError(DPOError):
    """Raised when scope setup save/restore fails."""
