import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client.js";

const defaultProgress = { value: 0, label: "0%", eta: "-", speed: "-", total: "-", logs: [] };

function inferProgress(raw) {
  const text = String(raw || "");
  const match = text.match(/(\d+(?:[.,]\d+)?)%/);
  if (!match) return null;
  const value = Number.parseFloat(match[1].replace(",", "."));
  if (!Number.isFinite(value)) return null;
  return { value, label: `${value.toFixed(1)}%` };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const pollTimerRef = useRef(null);
  const activeJobRef = useRef("");
  const [projects, setProjects] = useState([]);
  const [sourceMode, setSourceMode] = useState("rutube");
  const [sourceUrl, setSourceUrl] = useState("");
  const [localFile, setLocalFile] = useState(null);
  const [projectName, setProjectName] = useState("");
  const [status, setStatus] = useState("");
  const [importJobId, setImportJobId] = useState("");
  const [progress, setProgress] = useState(defaultProgress);
  const [importedVideo, setImportedVideo] = useState(null);
  const [isCreating, setIsCreating] = useState(false);

  const hasSource = sourceMode === "rutube" ? Boolean(sourceUrl.trim()) : Boolean(localFile);
  const canImport = hasSource && !importJobId;
  const canCreate = Boolean(importedVideo?.path) && !isCreating && !importJobId;

  const sortedProjects = useMemo(
    () => [...projects].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))),
    [projects]
  );

  const loadProjects = async () => {
    try {
      const data = await api.getProjects();
      setProjects(Array.isArray(data.projects) ? data.projects : []);
    } catch (err) {
      setStatus(err.message || "Failed to load projects.");
    }
  };

  useEffect(() => {
    loadProjects();
    return () => {
      isMountedRef.current = false;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    activeJobRef.current = "";
  };

  const updateProgressFromStatus = (data) => {
    const fromProgress = inferProgress(data.progress);
    const fromOutput = inferProgress(data.output);
    const candidate = fromProgress || fromOutput;
    setProgress((prev) => ({
      value: candidate?.value ?? prev.value,
      label: candidate?.label ?? prev.label,
      eta: data.eta || prev.eta || "-",
      speed: data.speed || prev.speed || "-",
      total: data.total || prev.total || "-",
      logs: Array.isArray(data.logs) ? data.logs.slice(-10) : prev.logs,
    }));
  };

  const pollDownload = async (id) => {
    if (!isMountedRef.current || activeJobRef.current !== id) return;
    let data;
    try {
      data = await api.getJobStatus(id);
    } catch (err) {
      if (!isMountedRef.current || activeJobRef.current !== id) return;
      stopPolling();
      setImportJobId("");
      setStatus(err.message || "Failed to fetch download status.");
      return;
    }
    if (!isMountedRef.current || activeJobRef.current !== id) return;
    updateProgressFromStatus(data);
    if (data.status === "done") {
      stopPolling();
      setImportJobId("");
      setImportedVideo({
        path: data.path || "",
        url: data.url || "",
        fileName: data.file || "",
        sourceType: "rutube",
      });
      setStatus("Video imported. Continue to project creation.");
      setProgress((prev) => ({ ...prev, value: 100, label: "100%" }));
      return;
    }
    if (data.status === "error" || data.status === "cancelled") {
      stopPolling();
      setImportJobId("");
      setStatus(data.output || data.status);
      return;
    }
    setStatus(data.output || "Downloading...");
    pollTimerRef.current = setTimeout(() => pollDownload(id), 900);
  };

  const importFromRutube = async () => {
    stopPolling();
    setProgress(defaultProgress);
    setImportedVideo(null);
    setStatus("Starting Rutube import...");
    let data;
    try {
      data = await api.startDownload(sourceUrl.trim());
    } catch (err) {
      setStatus(err.message || "Failed to start download.");
      return;
    }
    activeJobRef.current = data.job_id;
    setImportJobId(data.job_id);
    pollDownload(data.job_id);
  };

  const importFromLocal = async () => {
    if (!localFile) return;
    stopPolling();
    setProgress(defaultProgress);
    setImportedVideo(null);
    setStatus("Uploading local video...");
    let data;
    try {
      data = await api.uploadVideo(localFile);
    } catch (err) {
      setStatus(`Upload failed: ${err.message || "network error"}`);
      return;
    }
    setImportedVideo({
      path: data.path || "",
      url: data.url || "",
      fileName: data.file || localFile.name,
      sourceType: "local",
    });
    setProgress((prev) => ({ ...prev, value: 100, label: "100%" }));
    setStatus("Video imported. Continue to project creation.");
  };

  const onImport = async () => {
    if (!canImport) return;
    if (sourceMode === "rutube") {
      await importFromRutube();
      return;
    }
    await importFromLocal();
  };

  const createProject = async () => {
    if (!canCreate) return;
    setIsCreating(true);
    setStatus("Creating project...");
    let data;
    try {
      data = await api.createProject({
        name: projectName.trim() || "New project",
        sourceUrl: sourceMode === "rutube" ? sourceUrl.trim() : "",
        videoPath: importedVideo.path,
        transcriptPath: "data/audio_transcript.json",
      });
    } catch (err) {
      setIsCreating(false);
      setStatus(err.message || "Create project failed.");
      return;
    }
    setIsCreating(false);
    await loadProjects();
    navigate(`/editor/${data.id}`);
  };

  return (
    <div className="page-shell">
      <header className="page-topbar">
        <div>
          <h1 className="brand-title">Smart Clipper</h1>
          <p className="brand-subtitle">Import source video and create an edit-ready project.</p>
        </div>
      </header>

      <main className="dashboard-layout">
        <section className="card create-card">
          <div className="card-head">
            <h2>Create New Project</h2>
            <span className="head-tag">{sortedProjects.length} total projects</span>
          </div>

          <div className="flow-steps">
            <span className={`flow-step ${hasSource ? "done" : ""}`}>1. Source</span>
            <span className={`flow-step ${importedVideo ? "done" : ""}`}>2. Import</span>
            <span className={`flow-step ${canCreate ? "ready" : ""}`}>3. Create</span>
          </div>

          <div className="source-switch">
            <button
              className={`mode-btn ${sourceMode === "rutube" ? "active" : ""}`}
              onClick={() => setSourceMode("rutube")}
            >
              Rutube URL
            </button>
            <button
              className={`mode-btn ${sourceMode === "local" ? "active" : ""}`}
              onClick={() => setSourceMode("local")}
            >
              Local file
            </button>
          </div>

          {sourceMode === "rutube" ? (
            <input
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://rutube.ru/video/..."
            />
          ) : (
            <label className="file-input-v2">
              <input type="file" accept="video/*" onChange={(e) => setLocalFile(e.target.files?.[0] || null)} />
              <span>{localFile ? localFile.name : "Choose video from device"}</span>
            </label>
          )}

          <div className="wizard-actions">
            <button className="btn primary" onClick={onImport} disabled={!canImport}>
              {sourceMode === "rutube" ? "Download video" : "Upload video"}
            </button>
            <button
              className="btn danger"
              onClick={async () => {
                if (!importJobId) return;
                try {
                  await api.cancelDownload(importJobId);
                  stopPolling();
                  setStatus("Cancelling import...");
                } catch (err) {
                  setStatus(err.message || "Failed to cancel.");
                }
              }}
              disabled={!importJobId}
            >
              Cancel
            </button>
          </div>

          {(importJobId || progress.value > 0) && (
            <div className="progress-card">
              <div className="progress-head">
                <span>Import progress</span>
                <span>{progress.label}</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${progress.value}%` }} />
              </div>
              <div className="meta-row">
                <span>Speed: {progress.speed}</span>
                <span>ETA: {progress.eta}</span>
                <span>Total: {progress.total}</span>
              </div>
            </div>
          )}

          {importedVideo && (
            <div className="import-summary">
              <strong>Imported:</strong> {importedVideo.fileName || "video"} ({importedVideo.sourceType})
              {importedVideo.url && (
                <a href={importedVideo.url} className="video-link">
                  Open source
                </a>
              )}
            </div>
          )}

          <div className="project-create-row">
            <input value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="Project name" />
            <button className="btn success" onClick={createProject} disabled={!canCreate}>
              {isCreating ? "Creating..." : "Create project"}
            </button>
          </div>

          <div className="status-line">{status}</div>
        </section>

        <section className="card projects-card">
          <div className="card-head">
            <h2>Recent Projects</h2>
            <span className="head-tag">Open and continue editing</span>
          </div>
          <div className="project-grid">
            {sortedProjects.length === 0 && <div className="empty-card">No projects yet.</div>}
            {sortedProjects.map((project, idx) => (
              <Link key={project.id} to={`/editor/${project.id}`} className="project-card">
                <div className="project-thumb">#{idx + 1}</div>
                <div className="project-name">{project.name || `Project ${idx + 1}`}</div>
                <div className="project-date">{project.created_at || "-"}</div>
              </Link>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
