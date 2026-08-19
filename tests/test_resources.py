import pytest

from dpo4000_utils.channels import validate_channel
from dpo4000_utils.connection import build_tcpip_instr_resource, build_tcpip_socket_resource


def test_build_tcpip_instr_resource():
    assert build_tcpip_instr_resource("192.168.1.10") == "TCPIP0::192.168.1.10::INSTR"


def test_build_tcpip_socket_resource():
    assert build_tcpip_socket_resource("scope.local", 4000) == "TCPIP0::scope.local::4000::SOCKET"


def test_validate_channel_rejects_out_of_range():
    with pytest.raises(ValueError):
        validate_channel(5)
