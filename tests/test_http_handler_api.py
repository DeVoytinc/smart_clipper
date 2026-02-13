import http.client
import json
import threading
from http.server import HTTPServer
from threading import Thread
from urllib.parse import urlencode

import pytest

from clipserver import http_handler
from clipserver import routes


@pytest.fixture
def api_server(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    clips_dir = tmp_path / "clips"
    web_dir = tmp_path / "web"
    logs_dir = tmp_path / "logs"
    data_dir.mkdir()
    clips_dir.mkdir()
    web_dir.mkdir()
    logs_dir.mkdir()
    (web_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")

    monkeypatch.setattr(routes, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(routes, "CLIPS_DIR", str(clips_dir))
    monkeypatch.setattr(http_handler, "WEB_DIR", str(web_dir))
    monkeypatch.setattr(http_handler, "APP_LOG_PATH", str(logs_dir / "app.log"))
    monkeypatch.setattr(routes, "FRONTEND_LOG_PATH", str(logs_dir / "frontend.log"))

    with routes.JOB_LOCK:
        routes.JOB_STORE.clear()

    server = HTTPServer(("127.0.0.1", 0), http_handler.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        with routes.JOB_LOCK:
            routes.JOB_STORE.clear()


def _request(server_addr, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(server_addr[0], server_addr[1], timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    result = (resp.status, dict(resp.getheaders()), data)
    conn.close()
    return result


def _json(data):
    return json.loads(data.decode("utf-8"))


def test_upload_and_file_range(api_server):
    boundary = "----clipper-boundary"
    content = b"abcdefg12345"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="demo.mp4"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    status, headers, resp = _request(
        api_server,
        "POST",
        "/api/upload",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert status == 200
    assert headers.get("X-Request-ID")
    payload = _json(resp)
    assert payload["file"] == "demo.mp4"
    assert payload["url"] == "/files/demo.mp4"

    status, _, resp = _request(api_server, "GET", "/files/demo.mp4")
    assert status == 200
    assert resp == content

    status, headers, resp = _request(
        api_server,
        "GET",
        "/files/demo.mp4",
        headers={"Range": "bytes=0-3"},
    )
    assert status == 206
    assert headers.get("Content-Range") == "bytes 0-3/12"
    assert resp == b"abcd"


def test_upload_raw_binary_with_filename_header(api_server):
    content = b"raw-video-content"
    status, headers, resp = _request(
        api_server,
        "POST",
        "/api/upload",
        body=content,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Filename": "raw_upload.mp4",
        },
    )
    assert status == 200
    assert headers.get("X-Request-ID")
    payload = _json(resp)
    assert payload["file"] == "raw_upload.mp4"
    assert payload["url"] == "/files/raw_upload.mp4"


def test_upload_raw_binary_without_filename_header(api_server):
    content = b"raw-video-content-no-name"
    status, headers, resp = _request(
        api_server,
        "POST",
        "/api/upload",
        body=content,
        headers={"Content-Type": "video/mp4"},
    )
    assert status == 200
    assert headers.get("X-Request-ID")
    payload = _json(resp)
    assert payload["file"].startswith("upload_")
    assert payload["file"].endswith(".mp4")


def test_download_job_status_and_cancel(api_server, monkeypatch):
    def fake_download(job_id, _url):
        with routes.JOB_LOCK:
            routes.JOB_STORE[job_id]["status"] = "done"
            routes.JOB_STORE[job_id]["progress"] = "100%"
            routes.JOB_STORE[job_id]["output"] = "downloaded"

    monkeypatch.setattr(routes, "run_download_job", fake_download)
    monkeypatch.setattr(routes, "start_background", lambda target, args: target(*args))

    body = urlencode({"url": "https://rutube.ru/video/id"}).encode("utf-8")
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/download",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200
    job_id = _json(resp)["job_id"]

    status, _, resp = _request(api_server, "GET", f"/api/status?id={job_id}")
    assert status == 200
    payload = _json(resp)
    assert payload["status"] == "done"
    assert payload["progress"] == "100%"
    assert "cancel_event" not in payload

    with routes.JOB_LOCK:
        routes.JOB_STORE["c1"] = {
            "status": "running",
            "cancel_event": threading.Event(),
            "output": "running",
        }
    body = urlencode({"id": "c1"}).encode("utf-8")
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/cancel",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200
    assert _json(resp)["ok"] is True
    with routes.JOB_LOCK:
        assert routes.JOB_STORE["c1"]["status"] == "cancelling"


def test_project_save_validation_and_success(api_server, monkeypatch):
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/save",
        body=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert _json(resp)["error"] == "Invalid JSON"

    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/save",
        body=json.dumps({"project_id": ""}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert "project_id is required" in _json(resp)["error"]

    def fake_save(**kwargs):
        assert kwargs["project_id"] == "p1"
        assert len(kwargs["draft_clips"]) == 1
        assert kwargs["draft_clips"][0].start == 1.0
        assert kwargs["draft_clips"][0].kept is False
        assert kwargs["draft_clips"][0].score == 91.0
        assert kwargs["count"] == 8
        return {"id": "p1"}

    monkeypatch.setattr(routes, "save_project_state", fake_save)
    payload = {
        "project_id": "p1",
        "draft_clips": [{"id": "a", "start": 1, "end": 3, "kept": False, "score": 91}],
        "markers": [1.2],
        "selector": "both",
        "count": 8,
        "zoom": 1.2,
    }
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/save",
        body=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 200
    assert _json(resp)["ok"] is True

    monkeypatch.setattr(routes, "save_project_state", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/save",
        body=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 500
    assert _json(resp)["error"] == "boom"


def test_analyze_endpoint(api_server, monkeypatch, tmp_path):
    status, _, _ = _request(
        api_server,
        "POST",
        "/api/analyze",
        body=urlencode({"transcript": "missing.json", "selector": "both", "count": "8"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 400

    transcript = tmp_path / "audio_transcript.json"
    transcript.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(routes, "analyze_transcript", lambda _path, _selector, _count: [{"id": "c1", "start": 0, "end": 10}])
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/analyze",
        body=urlencode(
            {"transcript": str(transcript), "selector": "both", "count": "8"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200
    assert len(_json(resp)["clips"]) == 1


def test_export_endpoint_errors_and_success(api_server, monkeypatch):
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/export",
        body=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert _json(resp)["error"] == "Invalid JSON"

    status, _, resp = _request(
        api_server,
        "POST",
        "/api/export",
        body=json.dumps({"video": "", "clips": []}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert "video is required" in _json(resp)["error"]

    monkeypatch.setattr(routes, "export_project_clips", lambda **_: (_ for _ in ()).throw(FileNotFoundError()))
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/export",
        body=json.dumps(
            {
                "project_id": "p",
                "video": "x.mp4",
                "clips": [{"id": "c1", "start": 0, "end": 1}],
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert _json(resp)["error"] == "Video not found"

    monkeypatch.setattr(routes, "export_project_clips", lambda **_: (["clip_1.mp4"], "/clips"))
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/export",
        body=json.dumps(
            {
                "project_id": "p",
                "video": "x.mp4",
                "clips": [{"id": "c1", "start": 0, "end": 1}],
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 200
    payload = _json(resp)
    assert payload["files"] == ["clip_1.mp4"]
    assert payload["base"] == "/clips"


def test_projects_and_project_fetch(api_server, monkeypatch):
    monkeypatch.setattr(routes, "load_projects", lambda: [{"id": "p1", "created_at": "2026-02-12T10:00:00"}])
    monkeypatch.setattr(routes, "get_project_by_id", lambda _id: {"id": "p1"})

    status, _, resp = _request(api_server, "GET", "/api/projects")
    assert status == 200
    assert _json(resp)["projects"][0]["id"] == "p1"

    status, _, resp = _request(api_server, "GET", "/api/project?id=p1")
    assert status == 200
    assert _json(resp)["id"] == "p1"


def test_client_log_endpoint(api_server):
    status, headers, resp = _request(
        api_server,
        "POST",
        "/api/client-log",
        body=json.dumps({"message": "ui failed", "stack": "trace"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert status == 200
    assert headers.get("X-Request-ID")
    assert _json(resp)["ok"] is True


def test_project_create_handles_errors(api_server, monkeypatch):
    body = urlencode(
        {
            "name": "P1",
            "source_url": "",
            "video_path": "missing.mp4",
            "transcript_path": "data/audio_transcript.json",
        }
    ).encode("utf-8")

    monkeypatch.setattr(routes, "create_project", lambda *_: (_ for _ in ()).throw(FileNotFoundError()))
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/create",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 400
    assert _json(resp)["error"] == "Video not found"

    monkeypatch.setattr(routes, "create_project", lambda *_: (_ for _ in ()).throw(RuntimeError("create failed")))
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/create",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 500
    assert _json(resp)["error"] == "create failed"


def test_project_preview_endpoint(api_server, monkeypatch):
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/preview",
        body=urlencode({"id": ""}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 400
    assert "project id is required" in _json(resp)["error"]

    monkeypatch.setattr(routes, "ensure_project_preview", lambda *_args, **_kwargs: None)
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/preview",
        body=urlencode({"id": "missing", "force": "1"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 404
    assert _json(resp)["error"] == "Project not found"

    monkeypatch.setattr(
        routes,
        "ensure_project_preview",
        lambda *_args, **_kwargs: {
            "id": "p1",
            "video_url": "/files/projects/p1/preview_browser.mp4",
            "video_preview_path": "C:\\tmp\\preview_browser.mp4",
        },
    )
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/preview",
        body=urlencode({"id": "p1", "force": "1"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200
    payload = _json(resp)
    assert payload["ok"] is True
    assert payload["video_url"].endswith("preview_browser.mp4")


def test_project_thumbnails_endpoint(api_server, monkeypatch):
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/thumbnails",
        body=urlencode({"id": ""}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 400
    assert "project id is required" in _json(resp)["error"]

    monkeypatch.setattr(routes, "ensure_project_thumbnails", lambda *_args, **_kwargs: None)
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/thumbnails",
        body=urlencode({"id": "missing"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 404
    assert _json(resp)["error"] == "Project not found"

    monkeypatch.setattr(
        routes,
        "ensure_project_thumbnails",
        lambda *_args, **_kwargs: {
            "frames": [
                {"t": 0.0, "src": "/files/projects/p1/thumbs/frame_00001.jpg"},
                {"t": 10.0, "src": "/files/projects/p1/thumbs/frame_00002.jpg"},
            ]
        },
    )
    status, _, resp = _request(
        api_server,
        "POST",
        "/api/project/thumbnails",
        body=urlencode({"id": "p1", "force": "1", "count": "120"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200
    payload = _json(resp)
    assert payload["ok"] is True
    assert len(payload["frames"]) == 2
