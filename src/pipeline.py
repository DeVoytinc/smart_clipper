import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

VIDEO_FILE = "data/input2.mp4"
TRANSCRIPT_FILE = "data/audio_transcript.json"
OUTPUT_DIR = "clips"
OUTPUT_DIR_LLM = "clips_llm"
MIN_CLIP_DURATION_SEC = 30
MAX_CLIP_DURATION_SEC = 60
TARGET_CLIP_COUNT = int(os.getenv("TARGET_CLIP_COUNT", "8"))
CLIP_SELECTOR = os.getenv("CLIP_SELECTOR", "both").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR_LLM, exist_ok=True)

with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

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

RU_KEYWORDS_ESC = [
    "\u0441\u043c\u0435\u0448\u043d\u043e",
    "\u0448\u0443\u0442\u043a\u0430",
    "\u0430\u0445\u0430\u0445\u0430",
    "\u043b\u044e\u0431\u043b\u044e",
    "\u043d\u0435\u043d\u0430\u0432\u0438\u0436\u0443",
    "\u0441\u0435\u043a\u0440\u0435\u0442",
    "\u043f\u0440\u0430\u0432\u0434\u0430",
    "\u0441\u043c\u0435\u0440\u0442\u044c",
    "\u043e\u043f\u0430\u0441\u043d\u043e",
    "\u043f\u043e\u0447\u0435\u043c\u0443",
    "\u0437\u0430\u0447\u0435\u043c",
    "\u0436\u0438\u0437\u043d\u044c",
    "\u0441\u0443\u0434\u044c\u0431\u0430",
    "\u043d\u0435\u0432\u0435\u0440\u043e\u044f\u0442\u043d\u043e",
    "\u0448\u043e\u043a",
    "\u0441\u0442\u0440\u0430\u0445",
    "\u0443\u0436\u0430\u0441",
    "\u0432\u043f\u0435\u0440\u0432\u044b\u0435",
    "\u043d\u0438\u043a\u043e\u0433\u0434\u0430",
    "\u0432\u0441\u0435\u0433\u0434\u0430",
    "\u043f\u0440\u0435\u0434\u0430\u0442\u0435\u043b\u044c",
    "\u0441\u043c\u044b\u0441\u043b",
    "\u0437\u0430\u0434\u0443\u043c\u0430\u0439\u0441\u044f",
]

KEYWORDS = {
    "ru": [bytes(w, "utf-8").decode("unicode_escape") for w in RU_KEYWORDS_ESC],
    "en": [
        "funny", "joke", "haha", "lol", "sarcasm",
        "love", "hate", "fear", "shock", "secret", "truth", "lie",
        "kill", "death", "save", "danger", "betray",
        "why", "how", "never", "always", "first time",
        "meaning", "life", "fate", "unbelievable", "insane",
    ],
}

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def score_segment(seg) -> float:
    text = normalize_text(seg.get("text", ""))
    if not text:
        return 0.0

    score = 0.0
    score += text.count("!") * 0.7
    score += text.count("?") * 0.5
    score += text.count("...") * 0.3

    for kw in KEYWORDS["ru"]:
        if kw in text:
            score += 1.2
    for kw in KEYWORDS["en"]:
        if kw in text:
            score += 1.0

    word_count = len(text.split())
    if 4 <= word_count <= 22:
        score += 0.6
    elif word_count > 40:
        score -= 0.4

    return score


def build_clip_around_index(segments, center_idx, min_dur, max_dur):
    start_idx = center_idx
    end_idx = center_idx
    start = segments[start_idx]["start"]
    end = segments[end_idx]["end"]

    while end - start < min_dur and (start_idx > 0 or end_idx < len(segments) - 1):
        if start_idx > 0:
            start_idx -= 1
            start = segments[start_idx]["start"]
        if end - start >= min_dur:
            break
        if end_idx < len(segments) - 1:
            end_idx += 1
            end = segments[end_idx]["end"]

    while end - start > max_dur and start_idx < center_idx:
        start_idx += 1
        start = segments[start_idx]["start"]

    while end - start > max_dur and end_idx > center_idx:
        end_idx -= 1
        end = segments[end_idx]["end"]

    if end - start > max_dur:
        end = start + max_dur

    texts = [segments[i].get("text", "").strip() for i in range(start_idx, end_idx + 1)]
    return {
        "start": start,
        "end": end,
        "texts": texts,
        "center_idx": center_idx,
    }


def clips_overlap(a, b) -> bool:
    return not (a["end"] <= b["start"] or b["end"] <= a["start"])


def select_clips_heuristic(segments, min_dur, max_dur, target_count):
    scored = [(i, score_segment(seg)) for i, seg in enumerate(segments)]
    scored = [(i, s) for i, s in scored if s > 0.0]

    if not scored:
        return build_clips(segments, min_dur, max_dur)

    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = []
    max_candidates = min(len(scored), target_count * 6)
    for i, s in scored[:max_candidates]:
        clip = build_clip_around_index(segments, i, min_dur, max_dur)
        clip["score"] = s
        candidates.append(clip)

    candidates.sort(key=lambda c: c["score"], reverse=True)
    selected = []
    for c in candidates:
        if len(selected) >= target_count:
            break
        if all(not clips_overlap(c, s) for s in selected):
            selected.append(c)

    if len(selected) < target_count:
        fallback = build_clips(segments, min_dur, max_dur)
        for c in fallback:
            if len(selected) >= target_count:
                break
            if all(not clips_overlap(c, s) for s in selected):
                selected.append(c)

    return sorted(selected, key=lambda c: c["start"])


def build_units(segments, max_words=120, min_duration=20):
    units = []
    cur = None
    word_count = 0
    for seg in segments:
        text = seg.get("text", "").strip()
        if cur is None:
            cur = {
                "start": seg["start"],
                "end": seg["end"],
                "texts": [text],
                "score": score_segment(seg),
            }
            word_count = len(text.split())
            continue

        cur["end"] = seg["end"]
        cur["texts"].append(text)
        cur["score"] += score_segment(seg)
        word_count += len(text.split())

        if word_count >= max_words or (cur["end"] - cur["start"]) >= min_duration:
            units.append(cur)
            cur = None
            word_count = 0

    if cur is not None:
        units.append(cur)

    return units


def try_select_clips_llm(segments, min_dur, max_dur, target_count):
    if shutil.which("ollama") is None:
        print("LLM selection skipped: ollama not found.")
        return []

    units = build_units(segments)
    if len(units) > 200:
        units.sort(key=lambda u: u["score"], reverse=True)
        units = units[:160]
        units.sort(key=lambda u: u["start"])

    lines = []
    for idx, u in enumerate(units, start=1):
        text = " ".join(t for t in u["texts"] if t).strip()
        if not text:
            continue
        lines.append(
            f"{idx}. {u['start']:.2f}-{u['end']:.2f}: {text}"
        )

    prompt = (
        "Select interesting moments for YouTube Shorts from a movie transcript. "
        "Each line has start-end timestamps and text with an ID. "
        f"Pick {target_count} IDs (30-60s each), focusing on humor, emotion, "
        "dramatic tension, twists, or memorable quotes. "
        "Return ONLY a JSON array of integers (IDs), e.g. [3, 7, 12]. "
        "No extra keys, no markdown, no commentary. If unsure, return []. "
        "Use IDs from the provided lines, no overlap.\n\n"
        + "\n".join(lines)
    )

    raw = ""
    items = []
    # Prefer Ollama HTTP API with JSON enforcement
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "options": {"temperature": 0},
        }
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            api_body = resp.read().decode("utf-8", errors="replace")
        raw = api_body.strip()
        api_data = json.loads(api_body)
        response_text = api_data.get("response", "").strip()
        if response_text:
            try:
                parsed = json.loads(response_text)
                if isinstance(parsed, list):
                    items = parsed
            except json.JSONDecodeError:
                items = []
            if not items:
                arr_start = response_text.find("[")
                arr_end = response_text.rfind("]")
                if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
                    try:
                        items = json.loads(response_text[arr_start:arr_end + 1])
                    except json.JSONDecodeError:
                        items = []
            if not items:
                # Last resort: extract integers from response text
                ids = [int(x) for x in re.findall(r"\b\d+\b", response_text)]
                if ids:
                    items = ids
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        items = []

    if not items:
        # Fallback to CLI
        try:
            result = subprocess.run(
                ["ollama", "run", OLLAMA_MODEL],
                input=prompt.encode("utf-8"),
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr_bytes = exc.stderr or b""
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            print(f"LLM selection failed: {stderr or 'unknown ollama error'}")
            return []

        stdout_bytes = result.stdout or b""
        raw = stdout_bytes.decode("utf-8", errors="replace").strip()
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            items = []
            arr_start = raw.find("[")
            arr_end = raw.rfind("]")
            if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
                try:
                    items = json.loads(raw[arr_start:arr_end + 1])
                except json.JSONDecodeError:
                    items = []
            if not items:
                ids = [int(x) for x in re.findall(r"\b\d+\b", raw)]
                if ids:
                    items = ids
            if not items:
                print("LLM selection failed: invalid JSON response.")
                return []

    if raw:
        write_raw_llm(OUTPUT_DIR_LLM if CLIP_SELECTOR == "both" else OUTPUT_DIR, raw)

    # Map selected IDs to unit timestamps
    max_id = len(lines)
    selected_ids = []
    for item in items:
        try:
            idx = int(item)
        except (ValueError, TypeError):
            continue
        if 1 <= idx <= max_id:
            selected_ids.append(idx)
    # Deduplicate while preserving order
    seen = set()
    selected_ids = [x for x in selected_ids if not (x in seen or seen.add(x))]
    if not selected_ids:
        print("LLM selection failed: no valid IDs returned.")
        return []

    clips = []
    for idx in selected_ids:
        unit = units[idx - 1]
        start = float(unit["start"])
        end = float(unit["end"])
        if end <= start:
            continue
        if end - start < min_dur:
            end = start + min_dur
        if end - start > max_dur:
            end = start + max_dur

        texts = [seg.get("text", "").strip() for seg in segments if seg["start"] >= start and seg["end"] <= end]
        clips.append({"start": start, "end": end, "texts": texts, "reason": "llm_id"})

    filtered = []
    for c in sorted(clips, key=lambda c: c["start"]):
        if all(not clips_overlap(c, s) for s in filtered):
            filtered.append(c)
        if len(filtered) >= target_count:
            break

    return filtered

def build_clips(segments, min_duration_sec=MIN_CLIP_DURATION_SEC, max_duration_sec=MAX_CLIP_DURATION_SEC):
    """Merge neighboring segments into clips of min..max seconds."""
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


def export_clips(clips, output_dir):
    require_ffmpeg()
    os.makedirs(output_dir, exist_ok=True)
    for idx, seg in enumerate(clips):
        output_path = os.path.join(output_dir, f"clip_{idx}.mp4")
        export_video_clip(VIDEO_FILE, seg["start"], seg["end"], output_path)
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


def write_raw_llm(output_dir, raw_text, filename="selection_raw.txt"):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw_text or "")

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

segments = data.get("segments", [])

heuristic_clips = select_clips_heuristic(
    segments,
    MIN_CLIP_DURATION_SEC,
    MAX_CLIP_DURATION_SEC,
    TARGET_CLIP_COUNT,
)

llm_clips = []
if CLIP_SELECTOR in ("llm", "both"):
    llm_clips = try_select_clips_llm(
        segments,
        MIN_CLIP_DURATION_SEC,
        MAX_CLIP_DURATION_SEC,
        TARGET_CLIP_COUNT,
    )

if CLIP_SELECTOR == "llm":
    clips = llm_clips if llm_clips else heuristic_clips
    log_selected("LLM" if llm_clips else "Heuristic (fallback)", clips)
    if llm_clips:
        write_selection_json(llm_clips, OUTPUT_DIR)
    export_clips(clips, OUTPUT_DIR)
elif CLIP_SELECTOR == "heuristic":
    clips = heuristic_clips
    log_selected("Heuristic", clips)
    export_clips(clips, OUTPUT_DIR)
else:
    log_selected("Heuristic", heuristic_clips)
    export_clips(heuristic_clips, OUTPUT_DIR)
    if llm_clips:
        log_selected("LLM", llm_clips)
        write_selection_json(llm_clips, OUTPUT_DIR_LLM)
        export_clips(llm_clips, OUTPUT_DIR_LLM)


def print_summary(label, clips, output_dir):
    if clips:
        durations = [seg["end"] - seg["start"] for seg in clips]
        print(
            f"{label}: {len(clips)} clips in {output_dir}. "
            f"Duration range: {min(durations):.2f}s - {max(durations):.2f}s"
        )
    else:
        print(f"{label}: no clips generated.")

if CLIP_SELECTOR == "llm":
    print_summary("LLM", llm_clips if llm_clips else heuristic_clips, OUTPUT_DIR)
elif CLIP_SELECTOR == "heuristic":
    print_summary("Heuristic", heuristic_clips, OUTPUT_DIR)
else:
    print_summary("Heuristic", heuristic_clips, OUTPUT_DIR)
    if llm_clips:
        print_summary("LLM", llm_clips, OUTPUT_DIR_LLM)
