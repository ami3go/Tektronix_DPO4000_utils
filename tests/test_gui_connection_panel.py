import pytest


def test_connection_panel_exports_expected_constants():
    pytest.importorskip("tkinter")

    from dpo4000_utils.gui.connection_panel import CONNECTION_HINT_TEXT, CONNECTION_MODE_LABELS, ETHERNET_PROTOCOLS

    assert "TCPIP0::<ip>::INSTR" in CONNECTION_HINT_TEXT
    assert "TCPIP0::<ip>::4000::SOCKET" in CONNECTION_HINT_TEXT
    assert ETHERNET_PROTOCOLS == ("VXI-11 / INSTR", "Raw SOCKET")
    assert CONNECTION_MODE_LABELS == ("USB / VISA", "Ethernet")
