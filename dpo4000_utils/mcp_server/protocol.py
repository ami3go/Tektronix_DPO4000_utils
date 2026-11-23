"""MCP SDK v2 adapter for the opt-in read-only DPO4000 gateway."""

from __future__ import annotations

from typing import Any

from .gateway import ReadOnlyGateway


def build_server(gateway: ReadOnlyGateway) -> Any:
    """Register the v1 tool surface, without opening an instrument connection.

    Import the optional dependency here so regular DPO4000 users on Python 3.10
    can still import and use the driver without installing the MCP SDK.
    """
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "MCP support requires Python 3.11+ and the optional dependency: "
            "python -m pip install 'dpo4000-utils[mcp]'"
        ) from exc

    server = MCPServer("dpo4000-readonly")

    @server.tool()
    async def scope_get_status() -> dict[str, Any]:
        """Read MCP gateway status without touching an oscilloscope."""
        return gateway.status()

    @server.tool()
    async def scope_get_instrument_identity() -> dict[str, Any]:
        """Query the configured Tektronix oscilloscope *IDN? identity."""
        return await gateway.execute("identity")

    @server.tool()
    async def scope_get_channels() -> dict[str, Any]:
        """Read current CH1 through CH4 settings; do not modify any channel."""
        return await gateway.execute("channels")

    @server.tool()
    async def scope_get_measurement_slots() -> dict[str, Any]:
        """Read current MEAS1 through MEAS8 configuration and values."""
        return await gateway.execute("measurement_slots")

    @server.tool()
    async def scope_get_trigger_configuration() -> dict[str, Any]:
        """Read the active trigger configuration without changing the trigger."""
        return await gateway.execute("trigger")

    @server.tool()
    async def scope_get_acquisition_configuration() -> dict[str, Any]:
        """Read acquisition mode, record length and related scope settings."""
        return await gateway.execute("acquisition")

    @server.tool()
    async def scope_capture_preconfigured(
        max_points: int = 1000, preview_points: int = 128
    ) -> dict[str, Any]:
        """Read an already-configured CURVE? transfer.

        This tool never changes DATA:SOURCE, DATA:START/STOP, encoding, or
        acquisition settings. Transfers over max_points are rejected, not
        silently truncated. The returned preview is decimated, not a raw ADC
        stream, and is explicitly bounded.
        """
        return await gateway.execute(
            "capture_preconfigured", max_points=max_points, preview_points=preview_points
        )

    return server


__all__ = ["build_server"]
