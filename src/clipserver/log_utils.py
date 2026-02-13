import json
import os
import threading
import time
import uuid
from typing import Any, Dict

from .settings import LOG_DIR


_LOG_LOCK = threading.Lock()


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def write_jsonl(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False)
    with _LOG_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
