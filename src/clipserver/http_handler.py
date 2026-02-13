import json
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from .log_utils import new_request_id, now_iso, write_jsonl
from .routes import handle_get, handle_post
from .settings import APP_LOG_PATH, WEB_DIR


class Handler(BaseHTTPRequestHandler):
    def _start_request(self):
        self._request_started = time.time()
        self._request_id = new_request_id()
        self._last_status = None
        self._request_error = None

    def _log_request(self):
        duration_ms = int((time.time() - getattr(self, "_request_started", time.time())) * 1000)
        payload = {
            "timestamp": now_iso(),
            "level": "error" if self._request_error else "info",
            "request_id": getattr(self, "_request_id", ""),
            "method": self.command,
            "path": self.path,
            "status": self._last_status,
            "duration_ms": duration_ms,
            "error": self._request_error,
            "client": self.client_address[0] if self.client_address else "",
        }
        write_jsonl(APP_LOG_PATH, payload)

    def _send_json_error(self, code, message):
        if not self._request_error:
            self._request_error = message
        return self._send(code, json.dumps({"error": message}), "application/json")

    def _read_content_length(self):
        try:
            return int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return 0

    def _guess_upload_filename(self, content_type: str) -> str:
        if "mp4" in content_type:
            ext = ".mp4"
        elif "webm" in content_type:
            ext = ".webm"
        elif "quicktime" in content_type or "mov" in content_type:
            ext = ".mov"
        elif "x-matroska" in content_type or "mkv" in content_type:
            ext = ".mkv"
        elif "mpeg" in content_type:
            ext = ".mpeg"
        else:
            ext = ".bin"
        return f"upload_{int(time.time() * 1000)}{ext}"

    def _send(self, code, body, content_type="text/plain"):
        self._last_status = code
        self.send_response(code)
        self.send_header("X-Request-ID", getattr(self, "_request_id", ""))
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.wfile.write(body)

    def _serve_static(self, rel_path):
        rel_path = rel_path.lstrip("/")
        if not rel_path:
            rel_path = "index.html"
        safe_path = os.path.normpath(rel_path)
        if safe_path.startswith(".."):
            return self._send(403, "Forbidden")
        full_path = os.path.join(WEB_DIR, safe_path)
        if not os.path.isfile(full_path):
            if os.path.splitext(safe_path)[1] == "":
                full_path = os.path.join(WEB_DIR, "index.html")
                if os.path.isfile(full_path):
                    return self._serve_file(full_path)
            return self._send(404, "Not found")
        ext = os.path.splitext(full_path)[1].lower()
        content_type = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
        }.get(ext, "application/octet-stream")
        return self._serve_file(full_path, content_type)

    def _serve_file(self, full_path, content_type=None):
        ext = os.path.splitext(full_path)[1].lower()
        content_type = content_type or {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
        }.get(ext, "application/octet-stream")
        file_size = os.path.getsize(full_path)
        range_header = self.headers.get("Range")
        start = 0
        end = file_size - 1
        status = 200

        if range_header and range_header.startswith("bytes="):
            value = range_header.replace("bytes=", "", 1).strip()
            if "-" in value:
                left, right = value.split("-", 1)
                try:
                    if left.strip():
                        start = int(left)
                    if right.strip():
                        end = int(right)
                except ValueError:
                    start = 0
                    end = file_size - 1
                    status = 200
                else:
                    status = 206
            start = max(0, min(start, file_size - 1))
            end = max(start, min(end, file_size - 1))

        chunk_len = end - start + 1
        self._last_status = status
        self.send_response(status)
        self.send_header("X-Request-ID", getattr(self, "_request_id", ""))
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(chunk_len))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        with open(full_path, "rb") as f:
            f.seek(start)
            remaining = chunk_len
            while remaining > 0:
                buf = f.read(min(1024 * 1024, remaining))
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(buf)
        return None

    def do_GET(self):
        self._start_request()
        try:
            parsed = urlparse(self.path)
            return handle_get(self, parsed)
        except Exception as exc:
            self._request_error = str(exc)
            is_api = self.path.startswith("/api/")
            if is_api:
                return self._send_json_error(500, str(exc))
            return self._send(500, "Internal Server Error")
        finally:
            self._log_request()

    def do_POST(self):
        self._start_request()
        try:
            return handle_post(self)
        except Exception as exc:
            self._request_error = str(exc)
            is_api = self.path.startswith("/api/")
            if is_api:
                return self._send_json_error(500, str(exc))
            return self._send(500, "Internal Server Error")
        finally:
            self._log_request()
