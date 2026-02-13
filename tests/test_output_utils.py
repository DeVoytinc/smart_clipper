from output_utils import format_time


def test_format_time():
    assert format_time(0) == "00:00:00,000"
    assert format_time(1.234) == "00:00:01,234"
