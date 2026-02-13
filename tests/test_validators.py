import pytest

from clipserver.validators import (
    parse_analyze_form,
    parse_export_json,
    parse_project_create_form,
    parse_project_save_json,
)


def test_parse_project_create_form_defaults():
    req = parse_project_create_form(
        {
            "name": [""],
            "source_url": ["https://rutube.ru/video/abc"],
            "video_path": ["data/v.mp4"],
        }
    )
    assert req.name == "Untitled project"
    assert req.video_path == "data/v.mp4"
    assert req.transcript_path == "data/audio_transcript.json"


def test_parse_analyze_form_normalizes_count():
    req = parse_analyze_form({"transcript": ["t.json"], "selector": ["both"], "count": ["x"]})
    assert req.transcript == "t.json"
    assert req.selector == "both"
    assert req.count == 8


def test_parse_project_save_json_validates_project_id():
    with pytest.raises(ValueError):
        parse_project_save_json({})


def test_parse_project_save_json_filters_invalid_clips():
    req = parse_project_save_json(
        {
            "project_id": "p1",
            "draft_clips": [
                {"id": "ok", "start": 1, "end": 2, "kept": False, "score": "87.5"},
                {"id": "bad", "start": 3, "end": 1},
            ],
            "markers": ["1.5", "bad", 2],
            "selector": "llm",
            "count": "7",
            "zoom": "1.7",
        }
    )
    assert req.project_id == "p1"
    assert len(req.draft_clips) == 1
    assert req.draft_clips[0].kept is False
    assert req.draft_clips[0].score == 87.5
    assert req.markers == [1.5, 2.0]
    assert req.selector == "llm"
    assert req.count == 7
    assert req.zoom == 1.7


def test_parse_export_json_requires_video_and_valid_clip():
    with pytest.raises(ValueError):
        parse_export_json({"project_id": "p", "clips": []})

    with pytest.raises(ValueError):
        parse_export_json(
            {
                "project_id": "p",
                "video": "v.mp4",
                "clips": [{"id": "x", "start": 3, "end": 2}],
            }
        )

    req = parse_export_json(
        {
            "project_id": "p",
            "video": "v.mp4",
            "clips": [{"id": "x", "start": 1, "end": 2}],
        }
    )
    assert req.video == "v.mp4"
    assert len(req.clips) == 1
