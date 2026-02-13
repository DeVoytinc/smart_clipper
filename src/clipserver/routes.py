import json
import os
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse

from .jobs import JOB_LOCK, JOB_STORE, cleanup_jobs, run_download_job, run_pipeline_job, start_background
from .log_utils import now_iso, write_jsonl
from .media_utils import mime_for, parse_multipart_file, safe_join
from .project_store import load_projects
from .services import (
    analyze_transcript,
    create_project,
    ensure_project_preview,
    ensure_project_thumbnails,
    export_project_clips,
    get_project_by_id,
    save_project_state,
)
from .settings import CLIPS_DIR, DATA_DIR, FRONTEND_LOG_PATH, MAX_UPLOAD_BYTES
from .validators import (
    parse_analyze_form,
    parse_export_json,
    parse_project_create_form,
    parse_project_save_json,
)


def handle_get(handler, parsed):
    path = parsed.path
    if path.startswith("/api/"):
        path = path[4:] or "/"

    if path == "/projects":
        projects = load_projects()
        projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
        return handler._send(200, json.dumps({"projects": projects}), "application/json")
    if path == "/project":
        qs = parse_qs(parsed.query)
        project_id = (qs.get("id") or [""])[0]
        project = get_project_by_id(project_id)
        if not project:
            return handler._send_json_error(404, "Project not found")
        return handler._send(200, json.dumps(project), "application/json")
    if path == "/status":
        cleanup_jobs()
        qs = parse_qs(parsed.query)
        job_id = (qs.get("id") or [""])[0]
        with JOB_LOCK:
            job = JOB_STORE.get(job_id, {"status": "unknown"})
            if isinstance(job, dict) and "cancel_event" in job:
                job = dict(job)
                job.pop("cancel_event", None)
        return handler._send(200, json.dumps(job), "application/json")
    if path.startswith("/files/"):
        rel = path[len("/files/") :]
        if not rel:
            return handler._send(404, "Not found")
        full_path = safe_join(DATA_DIR, rel)
        if not full_path:
            return handler._send(403, "Forbidden")
        if not os.path.isfile(full_path):
            return handler._send(404, "Not found")
        return handler._serve_file(full_path, mime_for(full_path))
    if path.startswith("/clips/"):
        rel = path[len("/clips/") :]
        if not rel:
            return handler._send(404, "Not found")
        full_path = safe_join(CLIPS_DIR, rel)
        if not full_path:
            return handler._send(403, "Forbidden")
        if not os.path.isfile(full_path):
            return handler._send(404, "Not found")
        return handler._serve_file(full_path, mime_for(full_path))
    return handler._serve_static(path)


def handle_post(handler):
    path = urlparse(handler.path).path
    if path.startswith("/api/"):
        path = path[4:] or "/"

    if path == "/project/create":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        data = parse_qs(raw)
        req = parse_project_create_form(data)
        try:
            project = create_project(req.name, req.source_url, req.video_path, req.transcript_path)
        except FileNotFoundError:
            return handler._send_json_error(400, "Video not found")
        except Exception as exc:
            return handler._send_json_error(500, str(exc))
        return handler._send(200, json.dumps(project), "application/json")

    if path == "/project/save":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return handler._send_json_error(400, "Invalid JSON")
        try:
            req = parse_project_save_json(payload)
        except ValueError as exc:
            return handler._send_json_error(400, str(exc))
        try:
            project = save_project_state(
                project_id=req.project_id,
                draft_clips=req.draft_clips,
                markers=req.markers,
                selector=req.selector,
                count=req.count,
                zoom=req.zoom,
            )
        except KeyError:
            return handler._send_json_error(404, "Project not found")
        except Exception as exc:
            return handler._send_json_error(500, str(exc))
        return handler._send(200, json.dumps({"ok": True, "project": project}), "application/json")

    if path == "/project/preview":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        data = parse_qs(raw)
        project_id = (data.get("id") or [""])[0].strip()
        force = (data.get("force") or [""])[0].strip().lower() in ("1", "true", "yes")
        if not project_id:
            return handler._send_json_error(400, "project id is required")
        project = ensure_project_preview(project_id, force=force)
        if not project:
            return handler._send_json_error(404, "Project not found")
        return handler._send(
            200,
            json.dumps(
                {
                    "ok": True,
                    "video_url": project.get("video_url", ""),
                    "video_preview_path": project.get("video_preview_path", ""),
                }
            ),
            "application/json",
        )

    if path == "/project/thumbnails":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        data = parse_qs(raw)
        project_id = (data.get("id") or [""])[0].strip()
        force = (data.get("force") or [""])[0].strip().lower() in ("1", "true", "yes")
        count_raw = (data.get("count") or ["600"])[0].strip()
        try:
            count = int(count_raw) if count_raw else 600
        except ValueError:
            count = 600
        if not project_id:
            return handler._send_json_error(400, "project id is required")
        data = ensure_project_thumbnails(project_id, force=force, count=count)
        if data is None:
            return handler._send_json_error(404, "Project not found")
        return handler._send(200, json.dumps({"ok": True, "frames": data.get("frames", [])}), "application/json")

    if path == "/client-log":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"message": raw}
        write_jsonl(
            FRONTEND_LOG_PATH,
            {
                "timestamp": now_iso(),
                "level": "error",
                "request_id": getattr(handler, "_request_id", ""),
                "path": payload.get("path") or "",
                "message": payload.get("message") or "frontend_error",
                "stack": payload.get("stack") or "",
                "details": payload.get("details") or {},
            },
        )
        return handler._send(200, json.dumps({"ok": True}), "application/json")

    if path == "/cancel":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        data = parse_qs(raw)
        job_id = (data.get("id") or [""])[0].strip()
        with JOB_LOCK:
            job = JOB_STORE.get(job_id)
            if job and job.get("cancel_event"):
                job["cancel_event"].set()
                job["status"] = "cancelling"
                job["output"] = "cancelling..."
                return handler._send(200, json.dumps({"ok": True}), "application/json")
        return handler._send_json_error(404, "job not found")

    if path == "/upload":
        os.makedirs(DATA_DIR, exist_ok=True)
        length = handler._read_content_length()
        if length <= 0:
            return handler._send_json_error(400, "Empty upload body")
        if length > MAX_UPLOAD_BYTES:
            return handler._send_json_error(413, f"Upload too large (max {MAX_UPLOAD_BYTES} bytes)")
        raw_body = handler.rfile.read(length)
        raw_name = (handler.headers.get("X-Filename") or "").strip()
        content_type = (handler.headers.get("Content-Type") or "").lower()
        if raw_name or not content_type.startswith("multipart/form-data"):
            filename = os.path.basename(unquote(raw_name)) if raw_name else handler._guess_upload_filename(content_type)
            content = raw_body
        else:
            try:
                filename, content = parse_multipart_file(handler.headers, raw_body)
            except ValueError as exc:
                sample = raw_body[:220].decode("utf-8", errors="replace").replace("\r", "\\r").replace("\n", "\\n")
                extra = (
                    f"{exc}; content_type={handler.headers.get('Content-Type', '')}; "
                    f"content_length={length}; sample={sample}"
                )
                handler._request_error = extra
                return handler._send_json_error(400, str(exc))
        save_path = os.path.join(DATA_DIR, filename)
        with open(save_path, "wb") as f:
            f.write(content)
        return handler._send(
            200,
            json.dumps({"path": save_path, "file": filename, "url": f"/files/{filename}"}),
            "application/json",
        )

    if path == "/download":
        cleanup_jobs()
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        data = parse_qs(raw)
        url = (data.get("url") or [""])[0].strip()
        if not url:
            return handler._send_json_error(400, "No URL")
        job_id = str(int(time.time() * 1000))
        with JOB_LOCK:
            JOB_STORE[job_id] = {
                "status": "running",
                "started_at": time.time(),
                "output": "downloading",
                "progress": "0%",
                "eta": "",
                "speed": "",
                "total": "",
                "logs": [],
                "cancel_event": threading.Event(),
            }
        start_background(run_download_job, (job_id, url))
        return handler._send(200, json.dumps({"job_id": job_id}), "application/json")

    if path == "/analyze":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        data = parse_qs(raw)
        req = parse_analyze_form(data)
        if not req.transcript or not os.path.isfile(req.transcript):
            return handler._send_json_error(400, "Transcript not found")
        try:
            clips = analyze_transcript(req.transcript, req.selector, req.count)
            return handler._send(200, json.dumps({"clips": clips}), "application/json")
        except Exception as exc:
            return handler._send_json_error(500, str(exc))

    if path == "/export":
        length = handler._read_content_length()
        raw = handler.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return handler._send_json_error(400, "Invalid JSON")
        try:
            req = parse_export_json(payload)
            files, base = export_project_clips(
                project_id=req.project_id,
                video_path=req.video,
                clips=req.clips,
            )
            return handler._send(200, json.dumps({"files": files, "base": base}), "application/json")
        except ValueError as exc:
            return handler._send_json_error(400, str(exc))
        except FileNotFoundError:
            return handler._send_json_error(400, "Video not found")
        except Exception as exc:
            return handler._send_json_error(500, str(exc))

    if path != "/run":
        return handler._send(404, "Not found")

    cleanup_jobs()
    length = handler._read_content_length()
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    data = parse_qs(raw)

    url = (data.get("url") or [""])[0].strip()
    video = (data.get("video") or [""])[0].strip()
    transcript = (data.get("transcript") or [""])[0].strip()
    selector = (data.get("selector") or [""])[0].strip()
    count = (data.get("count") or [""])[0].strip()
    try:
        count = int(count) if count else None
    except ValueError:
        count = None

    job_id = str(int(time.time() * 1000))
    with JOB_LOCK:
        JOB_STORE[job_id] = {
            "status": "running",
            "started_at": time.time(),
            "output": "running",
            "cancel_event": threading.Event(),
        }
    start_background(run_pipeline_job, (job_id, url, video, transcript, selector, count))
    return handler._send(200, json.dumps({"job_id": job_id}), "application/json")
