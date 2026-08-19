from dpo4000_utils.waveform import parse_ascii_curve


def test_parse_ascii_curve():
    assert parse_ascii_curve("1, 2.5, -3\n") == [1.0, 2.5, -3.0]
