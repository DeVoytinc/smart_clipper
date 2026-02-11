import argparse
import json

from clip_utils import select_clips_heuristic
from config import (
    CLIP_SELECTOR,
    MAX_CLIP_DURATION_SEC,
    MIN_CLIP_DURATION_SEC,
    OLLAMA_MODEL,
    OUTPUT_DIR,
    OUTPUT_DIR_LLM,
    TARGET_CLIP_COUNT,
    TRANSCRIPT_FILE,
    VIDEO_FILE,
)
from downloader import download_rutube
from llm_selector import try_select_clips_llm
from output_utils import export_clips, log_selected, print_summary, write_selection_json


def parse_args():
    parser = argparse.ArgumentParser(description="Smart clipper pipeline")
    parser.add_argument("--download", help="Rutube video URL to download")
    parser.add_argument("--video", help="Path to input video file")
    parser.add_argument("--transcript", help="Path to transcript JSON file")
    return parser.parse_args()


def main():
    args = parse_args()

    video_path = args.video or VIDEO_FILE
    transcript_path = args.transcript or TRANSCRIPT_FILE

    if args.download:
        video_path = download_rutube(args.download, output_dir="data")

    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])

    heuristic_clips = select_clips_heuristic(
        segments,
        MIN_CLIP_DURATION_SEC,
        MAX_CLIP_DURATION_SEC,
        TARGET_CLIP_COUNT,
    )

    llm_clips = []
    if CLIP_SELECTOR in ("llm", "both"):
        raw_output_dir = OUTPUT_DIR_LLM if CLIP_SELECTOR == "both" else OUTPUT_DIR
        llm_clips = try_select_clips_llm(
            segments,
            MIN_CLIP_DURATION_SEC,
            MAX_CLIP_DURATION_SEC,
            TARGET_CLIP_COUNT,
            OLLAMA_MODEL,
            raw_output_dir,
        )

    if CLIP_SELECTOR == "llm":
        clips = llm_clips if llm_clips else heuristic_clips
        log_selected("LLM" if llm_clips else "Heuristic (fallback)", clips)
        if llm_clips:
            write_selection_json(llm_clips, OUTPUT_DIR)
        export_clips(clips, video_path, OUTPUT_DIR)
    elif CLIP_SELECTOR == "heuristic":
        clips = heuristic_clips
        log_selected("Heuristic", clips)
        export_clips(clips, video_path, OUTPUT_DIR)
    else:
        log_selected("Heuristic", heuristic_clips)
        export_clips(heuristic_clips, video_path, OUTPUT_DIR)
        if llm_clips:
            log_selected("LLM", llm_clips)
            write_selection_json(llm_clips, OUTPUT_DIR_LLM)
            export_clips(llm_clips, video_path, OUTPUT_DIR_LLM)

    if CLIP_SELECTOR == "llm":
        print_summary("LLM", llm_clips if llm_clips else heuristic_clips, OUTPUT_DIR)
    elif CLIP_SELECTOR == "heuristic":
        print_summary("Heuristic", heuristic_clips, OUTPUT_DIR)
    else:
        print_summary("Heuristic", heuristic_clips, OUTPUT_DIR)
        if llm_clips:
            print_summary("LLM", llm_clips, OUTPUT_DIR_LLM)


if __name__ == "__main__":
    main()
