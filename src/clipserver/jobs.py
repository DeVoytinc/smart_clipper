import os
import re
import subprocess
import threading
import time
from typing import Callable, Dict, Optional

from downloader import download_rutube_with_progress

from .settings import (
    DATA_DIR,
    JOB_MAX_LOG_LINES,
    JOB_MAX_OUTPUT_CHARS,
    JOB_TTL_SEC,
    PIPELINE_TIMEOUT_SEC,
)


JOB_STORE: Dict[str, Dict] = {}
JOB_LOCK = threading.Lock()


def _trim_output(text: str) -> str:
    if not text:
        return ""
    if len(text) <= JOB_MAX_OUTPUT_CHARS:
        return text
    return text[-JOB_MAX_OUTPUT_CHARS:]


def _mark_finished(job: Dict) -> None:
    job["finished_at"] = time.time()


def cleanup_jobs(now_ts: Optional[float] = None) -> None:
    now_ts = now_ts if now_ts is not None else time.time()
    with JOB_LOCK:
        stale = []
        for jid, job in JOB_STORE.items():
            finished_at = job.get("finished_at")
            if not finished_at:
                continue
            if now_ts - float(finished_at) > JOB_TTL_SEC:
                stale.append(jid)
        for jid in stale:
            JOB_STORE.pop(jid, None)


def run_pipeline_job(job_id, url, video, transcript, selector, count):
    with JOB_LOCK:
        job = JOB_STORE.get(job_id, {})
        cancel_event = job.get("cancel_event")

    env = os.environ.copy()
    if selector:
        env["CLIP_SELECTOR"] = selector
    if count:
        env["TARGET_CLIP_COUNT"] = str(count)

    cmd = ["python", "src/pipeline.py"]
    if url:
        cmd += ["--download", url]
    if video:
        cmd += ["--video", video]
    if transcript:
        cmd += ["--transcript", transcript]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        deadline = time.time() + PIPELINE_TIMEOUT_SEC
        status = "running"
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                status = "cancelled"
                break
            if time.time() > deadline:
                proc.terminate()
                status = "error"
                break
            time.sleep(0.25)

        stdout, stderr = proc.communicate(timeout=10)
        output = _trim_output((stdout or "") + (stderr or ""))
        if status == "running":
            status = "done" if proc.returncode == 0 else "error"
        elif status == "error" and time.time() > deadline:
            output = _trim_output((output + "\nPipeline timeout exceeded").strip())
        elif status == "cancelled":
            output = _trim_output((output + "\nPipeline cancelled").strip())
    except Exception as exc:
        output = f"Pipeline execution failed: {exc}"
        status = "error"

    with JOB_LOCK:
        if job_id in JOB_STORE:
            JOB_STORE[job_id]["status"] = status
            JOB_STORE[job_id]["output"] = output.strip() or status
            _mark_finished(JOB_STORE[job_id])


def run_download_job(job_id, url):
    with JOB_LOCK:
        cancel_event = JOB_STORE.get(job_id, {}).get("cancel_event") or threading.Event()
        JOB_STORE[job_id]["cancel_event"] = cancel_event

    def progress_cb(payload, line=None):
        with JOB_LOCK:
            if payload:
                parts = payload.split("|")
                percent_str = parts[0] if len(parts) > 0 else ""
                eta = parts[1] if len(parts) > 1 else ""
                speed = parts[2] if len(parts) > 2 else ""
                total = parts[3] if len(parts) > 3 else ""
                JOB_STORE[job_id]["progress"] = percent_str
                JOB_STORE[job_id]["eta"] = eta
                JOB_STORE[job_id]["speed"] = speed
                JOB_STORE[job_id]["total"] = total
                JOB_STORE[job_id]["output"] = f"downloading {percent_str} | {speed} | ETA {eta} | {total}"
            elif line:
                logs = JOB_STORE[job_id].setdefault("logs", [])
                logs.append(line)
                if len(logs) > JOB_MAX_LOG_LINES:
                    del logs[:-JOB_MAX_LOG_LINES]
                JOB_STORE[job_id]["output"] = line
                if "%" in line:
                    match = re.search(r"(\d+(?:[\.,]\d+)?)%", line)
                    if match:
                        JOB_STORE[job_id]["progress"] = match.group(1).replace(",", ".") + "%"

    try:
        path = download_rutube_with_progress(
            url,
            output_dir=DATA_DIR,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
        )
        filename = os.path.basename(path)
        with JOB_LOCK:
            JOB_STORE[job_id]["status"] = "done"
            JOB_STORE[job_id]["path"] = path
            JOB_STORE[job_id]["file"] = filename
            JOB_STORE[job_id]["url"] = f"/files/{filename}"
            JOB_STORE[job_id]["progress"] = "100%"
            JOB_STORE[job_id]["output"] = "downloaded"
            _mark_finished(JOB_STORE[job_id])
    except Exception as exc:
        with JOB_LOCK:
            msg = str(exc)
            if "cancelled" in msg:
                JOB_STORE[job_id]["status"] = "cancelled"
                JOB_STORE[job_id]["output"] = "download cancelled"
            else:
                JOB_STORE[job_id]["status"] = "error"
                JOB_STORE[job_id]["output"] = msg
            _mark_finished(JOB_STORE[job_id])


def start_background(target: Callable, args: tuple) -> None:
    t = threading.Thread(target=target, args=args, daemon=True)
    t.start()
