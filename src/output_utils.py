import json
import os

from ffmpeg_utils import export_video_clip, require_ffmpeg


def format_time(seconds):
    ms = int(seconds * 1000)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(clips, output_dir, filename="audio_subtitles.srt"):
    srt_path = os.path.join(output_dir, filename)
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(clips):
            f.write(f"{idx + 1}\n")
            f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
            f.write(" ".join(t for t in seg["texts"] if t).strip() + "\n\n")


def export_clips(clips, video_path, output_dir):
    require_ffmpeg()
    os.makedirs(output_dir, exist_ok=True)
    for idx, seg in enumerate(clips):
        output_path = os.path.join(output_dir, f"clip_{idx}.mp4")
        export_video_clip(video_path, seg["start"], seg["end"], output_path)
    write_srt(clips, output_dir)


def write_selection_json(clips, output_dir, filename="selection.json"):
    os.makedirs(output_dir, exist_ok=True)
    payload = []
    for seg in clips:
        payload.append(
            {
                "start": seg["start"],
                "end": seg["end"],
                "reason": seg.get("reason", ""),
                "text": " ".join(t for t in seg.get("texts", []) if t).strip(),
            }
        )
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def log_selected(label, clips):
    if not clips:
        print(f"{label}: no clips selected.")
        return
    print(f"{label}: selected {len(clips)} clips:")
    for idx, seg in enumerate(clips, start=1):
        text = " ".join(t for t in seg.get("texts", []) if t).strip()
        if len(text) > 160:
            text = text[:157] + "..."
        reason = seg.get("reason", "")
        reason_part = f" | reason: {reason}" if reason else ""
        print(f"  {idx}. {seg['start']:.2f}-{seg['end']:.2f}{reason_part} | {text}")


def print_summary(label, clips, output_dir):
    if clips:
        durations = [seg["end"] - seg["start"] for seg in clips]
        print(
            f"{label}: {len(clips)} clips in {output_dir}. "
            f"Duration range: {min(durations):.2f}s - {max(durations):.2f}s"
        )
    else:
        print(f"{label}: no clips generated.")
