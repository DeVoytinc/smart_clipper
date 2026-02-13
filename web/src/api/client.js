async function readJsonSafe(res) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { error: text || `HTTP ${res.status}` };
  }
}

function normalizeErrorMessage(message, status) {
  const text = String(message || "");
  if (text.includes("ECONNREFUSED") || text.includes("127.0.0.1:8000")) {
    return "Backend unavailable on http://127.0.0.1:8000. Start `python src/web_server.py`.";
  }
  if (status === 500 && text.includes("http proxy error")) {
    return "Backend connection failed via Vite proxy. Start backend on port 8000.";
  }
  if (status === 500 && !text.trim()) {
    return "Internal server error (empty response). Check logs/app.log.";
  }
  return text || `HTTP ${status}`;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function isNetworkError(err) {
  const text = String(err?.message || "");
  return (
    text.includes("Failed to fetch") ||
    text.includes("NetworkError") ||
    text.includes("ECONNREFUSED") ||
    text.includes("Load failed")
  );
}

async function request(url, options = {}) {
  const { retryAttempts, ...fetchOptions } = options;
  const method = String(fetchOptions.method || "GET").toUpperCase();
  const retryable = url.startsWith("/api/upload") || url.startsWith("/api/projects");
  const baseAttempts = retryable ? 4 : method === "GET" ? 2 : 1;
  const maxAttempts =
    Number.isInteger(retryAttempts) && retryAttempts > 0 ? retryAttempts : baseAttempts;
  let res;
  let lastErr;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      res = await fetch(url, fetchOptions);
      break;
    } catch (err) {
      lastErr = err;
      if (attempt < maxAttempts && isNetworkError(err)) {
        await sleep(300 * attempt);
        continue;
      }
      const text = String(err?.message || "");
      throw new Error(normalizeErrorMessage(text || "Network request failed", 0));
    }
  }

  if (!res) {
    const text = String(lastErr?.message || "");
    throw new Error(normalizeErrorMessage(text || "Network request failed", 0));
  }

  const requestId = res.headers.get("X-Request-ID") || "";
  const data = await readJsonSafe(res);
  if (!res.ok || data.error) {
    const error = new Error(normalizeErrorMessage(data.error, res.status));
    error.status = res.status;
    error.requestId = requestId;
    throw error;
  }
  if (requestId && typeof data === "object" && data !== null) {
    data.requestId = requestId;
  }
  return data;
}

export const api = {
  async clientLog(payload) {
    try {
      await fetch("/api/client-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
        keepalive: true,
      });
    } catch {
      // Intentionally ignored: logging must never break UI flow.
    }
  },
  getProjects() {
    return request("/api/projects");
  },
  getProject(projectId) {
    return request(`/api/project?id=${encodeURIComponent(projectId)}`, { retryAttempts: 3 });
  },
  getJobStatus(jobId) {
    return request(`/api/status?id=${encodeURIComponent(jobId)}`, { retryAttempts: 3 });
  },
  startDownload(url) {
    const body = new URLSearchParams();
    body.set("url", url);
    return request("/api/download", { method: "POST", body });
  },
  cancelDownload(jobId) {
    const body = new URLSearchParams();
    body.set("id", jobId);
    return request("/api/cancel", { method: "POST", body });
  },
  uploadVideo(file) {
    return request("/api/upload", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": encodeURIComponent(file?.name || "upload.mp4"),
      },
      body: file,
    });
  },
  createProject(payload) {
    const body = new URLSearchParams();
    body.set("name", payload.name || "Untitled project");
    body.set("source_url", payload.sourceUrl || "");
    body.set("video_path", payload.videoPath || "");
    body.set("transcript_path", payload.transcriptPath || "data/audio_transcript.json");
    return request("/api/project/create", { method: "POST", body });
  },
  saveProject(payload) {
    return request("/api/project/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      retryAttempts: 3,
    });
  },
  ensureProjectPreview(projectId, force = true) {
    const body = new URLSearchParams();
    body.set("id", projectId || "");
    body.set("force", force ? "1" : "0");
    return request("/api/project/preview", { method: "POST", body, retryAttempts: 2 });
  },
  ensureProjectThumbnails(projectId, force = false, count = 600) {
    const body = new URLSearchParams();
    body.set("id", projectId || "");
    body.set("force", force ? "1" : "0");
    body.set("count", String(count || 600));
    return request("/api/project/thumbnails", { method: "POST", body, retryAttempts: 2 });
  },
  analyze(payload) {
    const body = new URLSearchParams();
    body.set("transcript", payload.transcript || "");
    body.set("selector", payload.selector || "heuristic");
    body.set("count", String(payload.count || 8));
    return request("/api/analyze", { method: "POST", body, retryAttempts: 3 });
  },
  exportClips(payload) {
    return request("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
};
