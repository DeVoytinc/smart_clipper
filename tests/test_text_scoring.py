from text_scoring import normalize_text, score_segment


def test_normalize_text():
    assert normalize_text("  Hello   WORLD ") == "hello world"


def test_score_segment_empty():
    assert score_segment({"text": ""}) == 0.0


def test_score_segment_signal():
    score = score_segment({"text": "Wow! Why? unbelievable"})
    assert score > 0.0
