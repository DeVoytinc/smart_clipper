from clip_utils import build_clip_around_index, build_clips, build_units, clips_overlap


def test_build_clips_empty():
    assert build_clips([], 30, 60) == []


def test_clips_overlap():
    a = {"start": 0, "end": 10}
    b = {"start": 9, "end": 12}
    c = {"start": 10, "end": 12}
    assert clips_overlap(a, b) is True
    assert clips_overlap(a, c) is False


def test_build_clip_around_index_bounds():
    segments = [
        {"start": 0, "end": 5, "text": "a"},
        {"start": 5, "end": 12, "text": "b"},
        {"start": 12, "end": 20, "text": "c"},
    ]
    clip = build_clip_around_index(segments, 1, 10, 15)
    assert clip["start"] <= 5
    assert clip["end"] >= 12
    assert 10 <= (clip["end"] - clip["start"]) <= 15


def test_build_units_increases_count():
    segments = [{"start": i * 2, "end": i * 2 + 2, "text": "word"} for i in range(20)]
    units = build_units(segments, max_words=5, min_duration=4)
    assert len(units) > 0
