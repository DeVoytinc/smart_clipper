import json
import os
import shutil
import time
from typing import Dict, List, Optional, Tuple

from clip_utils import select_clips_heuristic
from config import MAX_CLIP_DURATION_SEC, MIN_CLIP_DURATION_SEC, OLLAMA_MODEL
from ffmpeg_utils import build_timeline_thumbnails, ensure_browser_preview
from llm_selector import try_select_clips_llm
from output_utils import export_clips, write_selection_json

from .contracts import ClipDraft
from .media_utils import public_data_url
from .project_store import find_project, load_projects, save_projects
from .settings import CLIPS_DIR, DATA_DIR, PROJECTS_DIR


def _preview_path_for(video_path: str) -> str:
    base_dir = os.path.dirname(video_path)
    return os.path.join(base_dir, "preview_browser.mp4")


def _hydrate_project_video(project: Dict) -> bool:
    """
    Ensure project has a browser-compatible preview URL when possible.
    Returns True if project fields were updated.
    """
    video_path = project.get("video_path") or ""
    if not video_path or not os.path.isfile(video_path):
        return False

    current_preview = project.get("video_preview_path") or ""
    if current_preview and os.path.isfile(current_preview):
        url = public_data_url(current_preview)
        changed = project.get("video_url") != url
        project["video_url"] = url
        return changed

    preview_path = _preview_path_for(video_path)
    selected_path = ensure_browser_preview(video_path, preview_path)
    if not selected_path or not os.path.isfile(selected_path):
        selected_path = video_path
    url = public_data_url(selected_path)

    changed = (
        project.get("video_preview_path") != selected_path
        or project.get("video_url") != url
    )
    project["video_preview_path"] = selected_path
    project["video_url"] = url
    return changed


def analyze_transcript(transcript_path: str, selector: str, count: int) -> List[Dict]:
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])
    clips = select_clips_heuristic(segments, MIN_CLIP_DURATION_SEC, MAX_CLIP_DURATION_SEC, count)
    if selector in ("llm", "both"):
        llm = try_select_clips_llm(
            segments,
            MIN_CLIP_DURATION_SEC,
            MAX_CLIP_DURATION_SEC,
            count,
            OLLAMA_MODEL,
            DATA_DIR,
        )
        if selector == "llm":
            clips = llm if llm else clips
        elif llm:
            clips = llm
    return clips


def create_project(name: str, source_url: str, video_path: str, transcript_path: str) -> Dict:
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError("Video not found")

    project_id = str(int(time.time() * 1000))
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    source_name = os.path.basename(video_path)
    project_video = os.path.join(project_dir, source_name)
    if os.path.abspath(video_path) != os.path.abspath(project_video):
        shutil.copy2(video_path, project_video)
    preview_video = ensure_browser_preview(project_video, _preview_path_for(project_video))
    if not preview_video or not os.path.isfile(preview_video):
        preview_video = project_video

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    project = {
        "id": project_id,
        "name": name or "Untitled project",
        "source_url": source_url,
        "video_path": project_video,
        "video_preview_path": preview_video,
        "video_url": public_data_url(preview_video),
        "transcript_path": transcript_path,
        "clips": [],
        "draft_clips": [],
        "markers": [],
        "selector": "both",
        "count": 8,
        "zoom": 1.2,
        "created_at": now,
        "updated_at": now,
    }
    projects = load_projects()
    projects.append(project)
    save_projects(projects)
    return project


def save_project_state(
    project_id: str,
    draft_clips: Optional[List[ClipDraft]],
    markers: Optional[List],
    selector: Optional[str],
    count: Optional[int],
    zoom: Optional[float],
) -> Dict:
    projects, project = find_project(project_id)
    if not project:
        raise KeyError("Project not found")

    if isinstance(draft_clips, list):
        sanitized = []
        for c in draft_clips:
            sanitized.append(
                {
                    "id": c.id,
                    "start": c.start,
                    "end": c.end,
                    "text": c.text,
                    "reason": c.reason,
                    "kept": bool(c.kept),
                    "score": c.score,
                }
            )
        project["draft_clips"] = sanitized

    if isinstance(markers, list):
        normalized_markers = []
        for m in markers:
            try:
                normalized_markers.append(float(m))
            except (TypeError, ValueError):
                continue
        project["markers"] = sorted(normalized_markers)

    if selector in ("both", "llm", "heuristic"):
        project["selector"] = selector

    if count is not None:
        try:
            project["count"] = int(count)
        except (TypeError, ValueError):
            pass

    if zoom is not None:
        try:
            project["zoom"] = float(zoom)
        except (TypeError, ValueError):
            pass

    project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_projects(projects)
    return project


def get_project_by_id(project_id: str) -> Optional[Dict]:
    projects, project = find_project(project_id)
    if not project:
        return None
    if _hydrate_project_video(project):
        project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_projects(projects)
    return project


def ensure_project_preview(project_id: str, force: bool = False) -> Optional[Dict]:
    projects, project = find_project(project_id)
    if not project:
        return None
    video_path = project.get("video_path") or ""
    if not video_path or not os.path.isfile(video_path):
        return None

    selected = project.get("video_preview_path") or ""
    preview_path = _preview_path_for(video_path)
    if force or not selected or not os.path.isfile(selected):
        selected = ensure_browser_preview(video_path, preview_path)
    if not selected or not os.path.isfile(selected):
        selected = video_path

    url = public_data_url(selected)
    changed = (
        project.get("video_preview_path") != selected
        or project.get("video_url") != url
    )
    project["video_preview_path"] = selected
    project["video_url"] = url
    if changed:
        project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        save_projects(projects)
    return project


def ensure_project_thumbnails(project_id: str, force: bool = False, count: int = 600) -> Optional[Dict]:
    projects, project = find_project(project_id)
    if not project:
        return None

    video_path = project.get("video_path") or ""
    if not video_path or not os.path.isfile(video_path):
        return None

    project_dir = os.path.dirname(video_path)
    thumbs_dir = os.path.join(project_dir, "thumbs")
    manifest_path = os.path.join(thumbs_dir, "index.json")

    if not force and os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                frames = json.load(f)
            if isinstance(frames, list) and frames:
                return {"frames": frames}
        except Exception:
            pass

    duration, files = build_timeline_thumbnails(video_path, thumbs_dir, count=count, width=120, height=68)
    if duration <= 0 or not files:
        return {"frames": []}

    step = duration / max(1, len(files) - 1)
    frames = []
    for idx, fp in enumerate(files):
        frames.append(
            {
                "t": round(min(duration, idx * step), 4),
                "src": public_data_url(fp),
            }
        )

    os.makedirs(thumbs_dir, exist_ok=True)
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(frames, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_projects(projects)
    return {"frames": frames}


def export_project_clips(project_id: str, video_path: str, clips: List[ClipDraft]) -> Tuple[List[str], str]:
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError("Video not found")

    target_dir = CLIPS_DIR
    base = "/clips/"
    if project_id:
        target_dir = os.path.join(CLIPS_DIR, project_id)
        base = f"/clips/{project_id}/"
    os.makedirs(target_dir, exist_ok=True)

    clip_dicts = [
        {"start": c.start, "end": c.end, "texts": [c.text] if c.text else [], "reason": c.reason}
        for c in clips
    ]
    export_clips(clip_dicts, video_path, target_dir)
    write_selection_json(clip_dicts, target_dir)
    files = [f for f in os.listdir(target_dir) if f.endswith(".mp4")]
    files.sort()

    if project_id:
        projects, project = find_project(project_id)
        if project:
            project["clips"] = [
                {
                    "file": f,
                    "url": f"{base}{f}",
                    "preview_url": f"{base}{f}",
                }
                for f in files
            ]
            project["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_projects(projects)

    return files, base
