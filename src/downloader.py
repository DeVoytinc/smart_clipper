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


def shutil_which(name: str) -> bool:
    try:
        from shutil import which
    except ImportError:
        return False
    return which(name) is not None
