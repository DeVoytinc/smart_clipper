import json
from pydub import AudioSegment
import os

AUDIO_FILE = "data/audio.wav"
TRANSCRIPT_FILE = "data/audio_transcript.json"
OUTPUT_DIR = "clips"
MIN_CLIP_DURATION_SEC = 30
MAX_CLIP_DURATION_SEC = 60

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

audio = AudioSegment.from_file(AUDIO_FILE)


def build_clips(segments, min_duration_sec=MIN_CLIP_DURATION_SEC, max_duration_sec=MAX_CLIP_DURATION_SEC):
    """Объединяет соседние транскрипт-сегменты в клипы длиной min..max секунд."""
    if not segments:
        return []

    clips = []
    current_clip = None

    for seg in segments:
        if current_clip is None:
            current_clip = {
                "start": seg["start"],
                "end": seg["end"],
                "texts": [seg.get("text", "").strip()],
            }
            continue

        candidate_duration = seg["end"] - current_clip["start"]

        if candidate_duration <= max_duration_sec:
            current_clip["end"] = seg["end"]
            current_clip["texts"].append(seg.get("text", "").strip())
            continue

        clips.append(current_clip)
        current_clip = {
            "start": seg["start"],
            "end": seg["end"],
            "texts": [seg.get("text", "").strip()],
        }

    if current_clip is not None:
        clips.append(current_clip)

    # Склеиваем слишком короткие клипы с соседями, если это укладывается в максимум.
    normalized = []
    i = 0
    while i < len(clips):
        clip = clips[i]
        duration = clip["end"] - clip["start"]

        if duration < min_duration_sec:
            if normalized:
                merged_prev_duration = clip["end"] - normalized[-1]["start"]
                if merged_prev_duration <= max_duration_sec:
                    normalized[-1]["end"] = clip["end"]
                    normalized[-1]["texts"].extend(clip["texts"])
                    i += 1
                    continue

            if i + 1 < len(clips):
                next_clip = clips[i + 1]
                merged_next_duration = next_clip["end"] - clip["start"]
                if merged_next_duration <= max_duration_sec:
                    normalized.append(
                        {
                            "start": clip["start"],
                            "end": next_clip["end"],
                            "texts": clip["texts"] + next_clip["texts"],
                        }
                    )
                    i += 2
                    continue

        normalized.append(clip)
        i += 1

    return normalized


clips = build_clips(data.get("segments", []))

# Нарезка клипов
for idx, seg in enumerate(clips):
    start_ms = int(seg["start"] * 1000)
    end_ms = int(seg["end"] * 1000)
    clip = audio[start_ms:end_ms]
    clip.export(f"{OUTPUT_DIR}/clip_{idx}.wav", format="wav")

# Создание SRT
def format_time(seconds):
    ms = int(seconds * 1000)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

with open(f"{OUTPUT_DIR}/audio_subtitles.srt", "w", encoding="utf-8") as f:
    for idx, seg in enumerate(clips):
        f.write(f"{idx + 1}\n")
        f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
        f.write(" ".join(t for t in seg["texts"] if t).strip() + "\n\n")

if clips:
    durations = [seg["end"] - seg["start"] for seg in clips]
    print(
        f"Generated {len(clips)} clips in {OUTPUT_DIR}. "
        f"Duration range: {min(durations):.2f}s - {max(durations):.2f}s"
    )
else:
    print("No clips generated: transcript has no segments")
