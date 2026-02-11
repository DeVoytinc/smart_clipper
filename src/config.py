import os

VIDEO_FILE = "data/input2.mp4"
TRANSCRIPT_FILE = "data/audio_transcript.json"
OUTPUT_DIR = "clips"
OUTPUT_DIR_LLM = "clips_llm"

MIN_CLIP_DURATION_SEC = 30
MAX_CLIP_DURATION_SEC = 60
TARGET_CLIP_COUNT = int(os.getenv("TARGET_CLIP_COUNT", "8"))
CLIP_SELECTOR = os.getenv("CLIP_SELECTOR", "both").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
