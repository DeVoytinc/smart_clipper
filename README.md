# Smart Clipper

## Environment

- Python: `3.12+`
- Node.js: `18+`

Install Python deps:

`pip install -r requirements-dev.txt`

Install frontend deps:

`cd web`
`npm.cmd install`

Quality checks:

- Backend tests: `python -m pytest -q`
- Frontend build: `cd web && npm.cmd run build`
- Lint (Python): `python -m ruff check src tests`
- Frontend smoke E2E: `cd web && npm.cmd run test:smoke`

## Debug Logs

The service writes structured logs to:

- `logs/app.log`: backend request logs (`request_id`, route, status, duration, error)
- `logs/frontend.log`: frontend runtime errors (`window.onerror`, `unhandledrejection`)

Each backend response includes `X-Request-ID`.  
When a bug happens, include this value in your report.

## Local Dev Startup

Run backend and frontend in separate terminals:

1. Backend:
`python src/web_server.py`

2. Frontend:
`cd web`
`npm.cmd run dev`

If frontend shows `ECONNREFUSED 127.0.0.1:8000`, backend is not running (or crashed).

### Shortcut

From `web/`, you can run only:
`npm.cmd run dev`

In dev mode Vite now auto-starts backend on `127.0.0.1:8000` if it is not running.

## Bug Report Template

Use this template for any issue:

```md
### Summary
Short description of the issue.

### Steps To Reproduce
1. ...
2. ...
3. ...

### Expected Result
What should happen.

### Actual Result
What happened instead.

### Context
- Time (local): YYYY-MM-DD HH:MM
- Route: /...
- Project ID: ...
- Request ID: ... (from response header `X-Request-ID` if available)

### Artifacts
- Screenshot / screen recording
- Relevant `logs/app.log` lines
- Relevant `logs/frontend.log` lines
```
