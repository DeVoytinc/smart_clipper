import mimetypes
import os
import re
from typing import Optional, Tuple

from .settings import DATA_DIR


def public_data_url(abs_path: str) -> str:
    normalized = os.path.abspath(abs_path).replace("\\", "/")
    base = os.path.abspath(DATA_DIR).replace("\\", "/")
    if normalized.startswith(base + "/"):
        rel = normalized[len(base) + 1 :]
        return f"/files/{rel}"
    return ""


def safe_join(base_dir: str, rel_path: str) -> Optional[str]:
    rel_path = (rel_path or "").replace("\\", "/").lstrip("/")
    target = os.path.abspath(os.path.join(base_dir, rel_path))
    base = os.path.abspath(base_dir)
    if not (target == base or target.startswith(base + os.sep)):
        return None
    return target


def mime_for(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def parse_multipart_file(headers, raw_body: bytes) -> Tuple[str, bytes]:
    content_type = headers.get("Content-Type", "")
    media_type, params = _parse_content_type(content_type)
    if media_type != "multipart/form-data":
        raise ValueError("Expected multipart/form-data")
    boundary = params.get("boundary")
    if not boundary:
        raise ValueError("Missing multipart boundary")

    boundary_bytes = ("--" + boundary).encode("utf-8")
    for raw_part in raw_body.split(boundary_bytes):
        part = raw_part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].rstrip(b"\r\n")

        header_blob, file_blob = _split_multipart_header_body(part)
        if header_blob is None:
            continue

        filename = _extract_filename(header_blob)
        if not filename:
            # Regular non-file multipart field.
            if b"name=" in header_blob.lower():
                continue
            raise ValueError("Missing uploaded filename")

        file_blob = file_blob.rstrip(b"\r\n")
        return os.path.basename(filename), file_blob
    raise ValueError("No file field in multipart body")


def _parse_content_type(value: str) -> Tuple[str, dict]:
    parts = [p.strip() for p in (value or "").split(";") if p.strip()]
    if not parts:
        return "", {}
    media_type = parts[0].lower()
    params = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, raw_val = part.split("=", 1)
        key = key.strip().lower()
        raw_val = raw_val.strip()
        if raw_val.startswith('"') and raw_val.endswith('"') and len(raw_val) >= 2:
            raw_val = raw_val[1:-1]
        params[key] = raw_val
    return media_type, params


def _extract_disposition_param(disposition_line: str, key: str) -> str:
    pattern = rf'{re.escape(key)}\s*=\s*(?:"([^"]*)"|([^;\s]+))'
    match = re.search(pattern, disposition_line, flags=re.IGNORECASE)
    if not match:
        return ""
    return (match.group(1) or match.group(2) or "").strip()


def _split_multipart_header_body(part: bytes):
    for sep in (b"\r\n\r\n", b"\n\n", b"\r\r"):
        if sep in part:
            return part.split(sep, 1)
    match = re.search(rb"\r?\n\r?\n", part)
    if match:
        idx = match.start()
        return part[:idx], part[match.end() :]
    return None, None


def _extract_filename(header_blob: bytes) -> str:
    text = header_blob.decode("utf-8", errors="replace")
    match = re.search(r'filename\*?=(?:"([^"]*)"|([^;\r\n]+))', text, flags=re.IGNORECASE)
    if not match:
        return ""
    value = (match.group(1) or match.group(2) or "").strip()
    if value.lower().startswith("utf-8''"):
        value = value[7:]
    return value
