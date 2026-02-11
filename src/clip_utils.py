from text_scoring import score_segment


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


def build_clips(segments, min_duration_sec, max_duration_sec):
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


def build_units(segments, max_words=80, min_duration=12):
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
