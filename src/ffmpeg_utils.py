import os
import shutil
import subprocess
from typing import List, Tuple


def require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("ffmpeg not found in PATH. Install ffmpeg and retry.")


def export_video_clip(video_path: str, start_sec: float, end_sec: float, output_path: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_sec:.3f}",
        "-to",
        f"{end_sec:.3f}",
        "-i",
        video_path,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-shortest",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg failed for {output_path}: {stderr}") from exc


def ensure_browser_preview(video_path: str, preview_path: str) -> str:
    """
    Build/update a browser-friendly MP4 preview (H.264/AAC).
    Returns preview_path on success, otherwise falls back to video_path.
    """
    if not video_path or not preview_path:
        return video_path
    if shutil.which("ffmpeg") is None:
        return video_path

    try:
        # Reuse existing preview when it is newer than source.
        if (
            preview_path != video_path
            and os.path.isfile(preview_path)
            and os.path.getmtime(preview_path) >= os.path.getmtime(video_path)
        ):
            return preview_path
    except OSError:
        pass

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        preview_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return preview_path
    except Exception:
        return video_path


def probe_duration(video_path: str) -> float:
    if not video_path or shutil.which("ffprobe") is None:
        return 0.0
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        video_path,
    ]
    try:
        out = subprocess.check_output(cmd, text=True).strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0


def build_timeline_thumbnails(
    video_path: str,
    out_dir: str,
    count: int = 120,
    width: int = 120,
    height: int = 68,
) -> Tuple[float, List[str]]:
    """
    Generate evenly spaced JPEG timeline thumbnails with ffmpeg.
    Returns (duration, absolute_paths_sorted).
    """
    if not video_path or not os.path.isfile(video_path):
        return 0.0, []
    if shutil.which("ffmpeg") is None:
        return 0.0, []

    duration = probe_duration(video_path)
    if duration <= 0:
        return 0.0, []

    safe_count = max(20, min(int(count or 120), 400))
    step = max(0.2, duration / max(1, safe_count - 1))

    os.makedirs(out_dir, exist_ok=True)
    for name in os.listdir(out_dir):
        if name.lower().endswith(".jpg"):
            try:
                os.remove(os.path.join(out_dir, name))
            except OSError:
                pass

    pattern = os.path.join(out_dir, "frame_%05d.jpg")
    vf = (
        f"fps=1/{step:.6f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vf",
        vf,
        "-q:v",
        "4",
        "-threads",
        "1",
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except Exception:
        return duration, []

    files = [
        os.path.join(out_dir, f)
        for f in os.listdir(out_dir)
        if f.lower().endswith(".jpg")
    ]
    files.sort()
    return duration, files
