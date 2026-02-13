import os


HOST = "127.0.0.1"
PORT = 8000

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_DIR = os.path.abspath(os.path.join(SRC_DIR, ".."))
WEB_ROOT = os.path.join(ROOT_DIR, "web")
WEB_DIR = os.path.join(WEB_ROOT, "dist") if os.path.isdir(os.path.join(WEB_ROOT, "dist")) else WEB_ROOT

DATA_DIR = os.path.join(ROOT_DIR, "data")
CLIPS_DIR = os.path.join(ROOT_DIR, "clips_ui")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
PROJECTS_META_PATH = os.path.join(DATA_DIR, "projects.json")
LOG_DIR = os.path.join(ROOT_DIR, "logs")
APP_LOG_PATH = os.path.join(LOG_DIR, "app.log")
FRONTEND_LOG_PATH = os.path.join(LOG_DIR, "frontend.log")

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GiB
JOB_TTL_SEC = 2 * 60 * 60
JOB_MAX_LOG_LINES = 300
PIPELINE_TIMEOUT_SEC = 60 * 45
JOB_MAX_OUTPUT_CHARS = 100_000
