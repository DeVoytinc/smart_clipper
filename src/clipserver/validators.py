from typing import Any, Dict, List

from .contracts import (
    AnalyzeRequest,
    ClipDraft,
    ExportRequest,
    ProjectCreateRequest,
    ProjectSaveRequest,
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def parse_clip_draft(item: Dict[str, Any], idx: int) -> ClipDraft:
    if not isinstance(item, dict):
        raise ValueError("Clip must be object")
    start = _as_float(item.get("start"), 0.0)
    end = _as_float(item.get("end"), 0.0)
    if end <= start:
        raise ValueError("Clip end must be greater than start")
    score_value = item.get("score")
    try:
        score = float(score_value) if score_value is not None else None
    except (TypeError, ValueError):
        score = None
    return ClipDraft(
        id=str(item.get("id") or f"clip-{idx}"),
        start=start,
        end=end,
        text=str(item.get("text") or ""),
        reason=str(item.get("reason") or ""),
        kept=_as_bool(item.get("kept"), True),
        score=score,
    )


def parse_project_create_form(data: Dict[str, List[str]]) -> ProjectCreateRequest:
    name = (data.get("name") or [""])[0].strip() or "Untitled project"
    source_url = (data.get("source_url") or [""])[0].strip()
    video_path = (data.get("video_path") or [""])[0].strip()
    transcript_path = (data.get("transcript_path") or ["data/audio_transcript.json"])[0].strip()
    return ProjectCreateRequest(
        name=name,
        source_url=source_url,
        video_path=video_path,
        transcript_path=transcript_path,
    )


def parse_analyze_form(data: Dict[str, List[str]]) -> AnalyzeRequest:
    transcript = (data.get("transcript") or [""])[0].strip()
    selector = (data.get("selector") or ["heuristic"])[0].strip() or "heuristic"
    count = _as_int((data.get("count") or ["8"])[0], 8)
    return AnalyzeRequest(transcript=transcript, selector=selector, count=max(1, count))


def parse_project_save_json(payload: Dict[str, Any]) -> ProjectSaveRequest:
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("project_id is required")

    draft_clips = []
    for idx, c in enumerate(payload.get("draft_clips") or []):
        try:
            draft_clips.append(parse_clip_draft(c, idx))
        except ValueError:
            continue

    markers = []
    for marker in payload.get("markers") or []:
        try:
            markers.append(float(marker))
        except (TypeError, ValueError):
            continue

    selector = str(payload.get("selector") or "both")
    count = _as_int(payload.get("count"), 8)
    zoom = _as_float(payload.get("zoom"), 1.2)

    return ProjectSaveRequest(
        project_id=project_id,
        draft_clips=draft_clips,
        markers=markers,
        selector=selector,
        count=count,
        zoom=zoom,
    )


def parse_export_json(payload: Dict[str, Any]) -> ExportRequest:
    video = str(payload.get("video") or "").strip()
    if not video:
        raise ValueError("video is required")
    project_id = str(payload.get("project_id") or "").strip()
    clips = []
    for idx, c in enumerate(payload.get("clips") or []):
        clips.append(parse_clip_draft(c, idx))
    return ExportRequest(project_id=project_id, video=video, clips=clips)
