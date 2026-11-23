"""In-process MCP SDK v2 contract tests; never use a physical oscilloscope."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402
from dpo4000_utils.mcp_server.gateway import ReadOnlyGateway  # noqa: E402
from dpo4000_utils.mcp_server.protocol import build_server  # noqa: E402


def test_mcp_server_lists_bounded_read_only_tools():
    gateway = ReadOnlyGateway()
    try:
        server = build_server(gateway)

        async def check():
            async with Client(server) as client:
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                assert names == {
                    "scope_get_status",
                    "scope_get_instrument_identity",
                    "scope_get_channels",
                    "scope_get_measurement_slots",
                    "scope_get_trigger_configuration",
                    "scope_get_acquisition_configuration",
                    "scope_capture_preconfigured",
                }
                result = await client.call_tool("scope_get_status", {})
                assert not result.is_error
                assert result.structured_content["instrument_io_enabled"] is False
                assert result.structured_content["resource_configured"] is False

        asyncio.run(check())
    finally:
        gateway.close()
