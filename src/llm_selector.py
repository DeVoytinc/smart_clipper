import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request

from clip_utils import build_units, clips_overlap


def write_raw_llm(output_dir, raw_text, filename="selection_raw.txt"):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw_text or "")


def try_select_clips_llm(segments, min_dur, max_dur, target_count, model_name, raw_output_dir):
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
        lines.append(f"{idx}. {u['start']:.2f}-{u['end']:.2f}: {text}")

    prompt = (
        "Select interesting moments for YouTube Shorts from a movie transcript. "
        "Each line has start-end timestamps and text with an ID. "
        f"Pick {target_count} IDs (30-60s each), focusing on humor, emotion. "
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
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": {"type": "array", "items": {"type": "integer"}},
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
                ids = [int(x) for x in re.findall(r"\b\d+\b", response_text)]
                if ids:
                    items = ids
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        items = []

    if not items:
        # Fallback to CLI
        try:
            result = subprocess.run(
                ["ollama", "run", model_name],
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
                write_raw_llm(raw_output_dir, raw)
                print("LLM selection failed: invalid JSON response.")
                return []

    if raw:
        write_raw_llm(raw_output_dir, raw)

    max_id = len(lines)
    selected_ids = []
    for item in items:
        try:
            idx = int(item)
        except (ValueError, TypeError):
            continue
        if 1 <= idx <= max_id:
            selected_ids.append(idx)

    seen = set()
    selected_ids = [x for x in selected_ids if not (x in seen or seen.add(x))]
    if not selected_ids:
        print("LLM selection failed: no valid IDs returned.")
        return []

    # If LLM returned too few IDs, fill with top-scoring units
    if len(selected_ids) < target_count:
        scored_units = [(i + 1, u.get("score", 0.0)) for i, u in enumerate(units)]
        scored_units.sort(key=lambda x: x[1], reverse=True)
        for unit_id, _ in scored_units:
            if len(selected_ids) >= target_count:
                break
            if unit_id not in selected_ids:
                selected_ids.append(unit_id)

    clips = []
    for idx in selected_ids[:target_count]:
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
