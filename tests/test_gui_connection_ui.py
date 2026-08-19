from __future__ import annotations

import pytest

from dpo4000_utils.gui.connection_ui import (
    ETHERNET_SOCKET_PROTOCOL,
    ETHERNET_VXI11_PROTOCOL,
    build_ethernet_resource,
    parse_timeout_ms,
    parse_trigger_channel,
    parse_trigger_level,
    selected_resource_name,
)


def test_build_vxi11_ethernet_resource() -> None:
    assert build_ethernet_resource("192.168.1.20", ETHERNET_VXI11_PROTOCOL) == "TCPIP0::192.168.1.20::INSTR"


def test_build_socket_ethernet_resource() -> None:
    assert build_ethernet_resource("scope.local", ETHERNET_SOCKET_PROTOCOL, "4000") == "TCPIP0::scope.local::4000::SOCKET"


@pytest.mark.parametrize("port", ["0", "65536", "abc"])
def test_socket_port_validation(port: str) -> None:
    with pytest.raises(ValueError):
        build_ethernet_resource("192.168.1.20", ETHERNET_SOCKET_PROTOCOL, port)


def test_selected_resource_uses_visa_mode() -> None:
    assert selected_resource_name("visa", "USB0::SCOPE::INSTR", "", ETHERNET_VXI11_PROTOCOL, "4000") == "USB0::SCOPE::INSTR"


def test_selected_resource_uses_ethernet_mode() -> None:
    assert (
        selected_resource_name("ethernet", "USB0::SCOPE::INSTR", "10.0.0.5", ETHERNET_VXI11_PROTOCOL, "4000")
        == "TCPIP0::10.0.0.5::INSTR"
    )


def test_timeout_validation() -> None:
    assert parse_timeout_ms("20000") == 20000
    with pytest.raises(ValueError):
        parse_timeout_ms("999")
    with pytest.raises(ValueError):
        parse_timeout_ms("slow")


def test_trigger_channel_parser() -> None:
    assert parse_trigger_channel("1") == 1
    assert parse_trigger_channel("", allow_empty=True) is None
    with pytest.raises(ValueError):
        parse_trigger_channel("5")


def test_trigger_level_parser() -> None:
    assert parse_trigger_level("1.25") == 1.25
    assert parse_trigger_level("ttl") == "TTL"
    assert parse_trigger_level("ECL") == "ECL"
    with pytest.raises(ValueError):
        parse_trigger_level("")
