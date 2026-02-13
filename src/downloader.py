import os
import re
import subprocess
from urllib.parse import urlparse


def _extract_rutube_id(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # Expected: video/<id>/
    match = re.search(r"video/([a-f0-9]{32})", path, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: last path segment
    parts = [p for p in path.split("/") if p]
    return parts[-1] if parts else "rutube_video"


def download_rutube(url: str, output_dir: str = "data") -> str:
    if not shutil_which("yt-dlp"):
        raise FileNotFoundError("yt-dlp not found in PATH. Install yt-dlp and retry.")

    video_id = _extract_rutube_id(url)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"rutube_{video_id}.mp4")

    cmd = [
        "yt-dlp",
        "-f",
        "bv*+ba/best",
        "--merge-output-format",
        "mp4",
        "-o",
        output_path,
        url,
    ]
    subprocess.run(cmd, check=True)
    return output_path


def download_rutube_with_progress(url: str, output_dir: str, progress_cb, cancel_event=None):
    if not shutil_which("yt-dlp"):
        raise FileNotFoundError("yt-dlp not found in PATH. Install yt-dlp and retry.")

    video_id = _extract_rutube_id(url)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"rutube_{video_id}.mp4")

    cmd = [
        "yt-dlp",
        "-f",
        "bv*+ba/best",
        "--merge-output-format",
        "mp4",
        "--newline",
        "--progress-template",
        "download:%(progress._percent_str)s|%(progress._eta_str)s|%(progress._speed_str)s|%(progress._total_bytes_str)s",
        "-o",
        output_path,
        url,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        for line in proc.stdout:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                raise RuntimeError("download cancelled")
            line = line.strip()
            if line.startswith("download:"):
                payload = line.split("download:", 1)[1].strip()
                progress_cb(payload)
            else:
                progress_cb(None, line)

    ret = proc.wait()
    if ret != 0:
        raise RuntimeError("yt-dlp failed")
    return output_path


def shutil_which(name: str) -> bool:
    try:
        from shutil import which
    except ImportError:
        return False
    return which(name) is not None
