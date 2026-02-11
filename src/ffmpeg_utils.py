import shutil
import subprocess


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
