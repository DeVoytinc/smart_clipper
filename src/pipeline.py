import json
from pydub import AudioSegment
import os

AUDIO_FILE = "data/audio.wav"
TRANSCRIPT_FILE = "data/audio_transcript.json"
OUTPUT_DIR = "clips"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

audio = AudioSegment.from_file(AUDIO_FILE)

# Нарезка клипов
for seg in data["segments"]:
    start_ms = int(seg["start"] * 1000)
    end_ms = int(seg["end"] * 1000)
    clip = audio[start_ms:end_ms]
    clip.export(f"{OUTPUT_DIR}/clip_{seg['id']}.wav", format="wav")

# Создание SRT
def format_time(seconds):
    ms = int(seconds * 1000)
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

with open(f"{OUTPUT_DIR}/audio_subtitles.srt", "w", encoding="utf-8") as f:
    for seg in data["segments"]:
        f.write(f"{seg['id']+1}\n")
        f.write(f"{format_time(seg['start'])} --> {format_time(seg['end'])}\n")
        f.write(seg["text"].strip() + "\n\n")

print("Clips and SRT generated in ../clips")
