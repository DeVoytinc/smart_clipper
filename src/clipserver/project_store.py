import json
import os
import tempfile
import threading
from typing import Dict, List, Optional, Tuple

from .settings import DATA_DIR, PROJECTS_META_PATH


PROJECTS_LOCK = threading.Lock()


def load_projects() -> List[Dict]:
    with PROJECTS_LOCK:
        if not os.path.isfile(PROJECTS_META_PATH):
            return []
        try:
            with open(PROJECTS_META_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []


def save_projects(projects: List[Dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with PROJECTS_LOCK:
        fd, tmp_path = tempfile.mkstemp(prefix="projects_", suffix=".json", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(projects, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, PROJECTS_META_PATH)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


def find_project(project_id: str) -> Tuple[List[Dict], Optional[Dict]]:
    projects = load_projects()
    for item in projects:
        if str(item.get("id")) == str(project_id):
            return projects, item
    return projects, None

