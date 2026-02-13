import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client.js";
import { useFrames } from "../features/editor/useFrames.js";
import { MIN_CLIP_SEC, clamp, formatTime, normalizeClips } from "../features/editor/utils.js";
import PhaseStepper from "../features/project-flow/PhaseStepper.jsx";

const BASE_PX_PER_SEC = 48;
const MAX_ZOOM = 12;
const FALLBACK_MIN_ZOOM = 0.01;
const RULER_HEIGHT = 24;
const FRAMES_HEIGHT = 46;
const TRACK_HEIGHT = 46;
const MARKERS_HEIGHT = 38;
const DEFAULT_TRACKS = ["V1", "V2", "V3"];
const FRAME_TILE_WIDTH = 96;
const FRAME_TILE_BUFFER = 6;

function asExportItems(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => {
      if (!item) return null;
      if (typeof item === "string") {
        return { file: item, url: `/clips/${item}`, preview_url: `/clips/${item}` };
      }
      if (typeof item === "object") {
        const file = item.file || item.name || "";
        const url = item.url || (file ? `/clips/${file}` : "");
        return {
          file: file || (url ? url.split("/").pop() : "clip"),
          url,
          preview_url: item.preview_url || url,
        };
      }
      return null;
    })
    .filter(Boolean);
}

function enrichClips(items) {
  return normalizeClips(items).map((clip, idx) => ({
    ...clip,
    kept: clip.kept !== false,
    score: Number.isFinite(Number(clip.score)) ? Number(clip.score) : Math.max(50, 95 - idx * 6),
  }));
}

export default function ProjectEditor() {
  const { projectId } = useParams();
  const videoRef = useRef(null);
  const timelineViewportRef = useRef(null);
  const dirtyTimeoutRef = useRef(null);
  const dragDirtyRef = useRef(false);

  const [project, setProject] = useState(null);
  const [status, setStatus] = useState("");
  const [autosaveError, setAutosaveError] = useState("");
  const [mediaUnsupported, setMediaUnsupported] = useState(false);
  const [phase, setPhase] = useState("generate");
  const [selector, setSelector] = useState("both");
  const [count, setCount] = useState("8");
  const [trackOrder, setTrackOrder] = useState(DEFAULT_TRACKS);
  const [clips, setClips] = useState([]);
  const [selectedClipIds, setSelectedClipIds] = useState([]);
  const [activeClipId, setActiveClipId] = useState("");
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [zoom, setZoom] = useState(1.2);
  const [markers, setMarkers] = useState([]);
  const [dragState, setDragState] = useState(null);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [timelineView, setTimelineView] = useState({ left: 0, width: 0 });
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isProjectSaving, setIsProjectSaving] = useState(false);
  const [isRecoveringPreview, setIsRecoveringPreview] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [dirtyVersion, setDirtyVersion] = useState(0);
  const [exported, setExported] = useState([]);
  const [serverFrames, setServerFrames] = useState([]);

  const timelineViewportWidth = timelineView.width || 1100;
  const minZoom = useMemo(() => {
    if (!duration || !timelineViewportWidth) return FALLBACK_MIN_ZOOM;
    const fitPxPerSec = timelineViewportWidth / Math.max(duration, 1);
    const fitZoom = fitPxPerSec / BASE_PX_PER_SEC;
    return clamp(fitZoom * 0.96, FALLBACK_MIN_ZOOM, 1);
  }, [duration, timelineViewportWidth]);
  const pxPerSec = BASE_PX_PER_SEC * zoom;
  const timelineWidth = Math.max(900, duration * pxPerSec);
  const activeClip = clips.find((clip) => clip.id === activeClipId) || null;
  const selectedSet = useMemo(() => new Set(selectedClipIds), [selectedClipIds]);
  const keptClips = useMemo(() => clips.filter((clip) => clip.kept !== false), [clips]);
  const browserFrames = useFrames(project?.video_url, duration);
  const frames = serverFrames.length ? serverFrames : browserFrames;
  const sortedFrames = useMemo(
    () =>
      [...frames]
        .map((f) => ({ t: Number(f?.t) || 0, src: String(f?.src || "") }))
        .filter((f) => f.src)
        .sort((a, b) => a.t - b.t),
    [frames]
  );
  const visibleWindowSec = useMemo(() => {
    if (!timelineViewportWidth || !pxPerSec) return 0;
    return timelineViewportWidth / pxPerSec;
  }, [timelineViewportWidth, pxPerSec]);
  const timelineHeight = useMemo(
    () => RULER_HEIGHT + FRAMES_HEIGHT + trackOrder.length * TRACK_HEIGHT + MARKERS_HEIGHT,
    [trackOrder.length]
  );
  const zoomSlider = useMemo(() => {
    const min = Math.max(minZoom, FALLBACK_MIN_ZOOM);
    const max = MAX_ZOOM;
    const clamped = clamp(zoom, min, max);
    if (min === max) return 100;
    const t = (Math.log(clamped) - Math.log(min)) / (Math.log(max) - Math.log(min));
    return Math.round(clamp(t, 0, 1) * 100);
  }, [zoom, minZoom]);

  const markDirty = () => setDirtyVersion((prev) => prev + 1);

  const loadProject = async () => {
    let data;
    setServerFrames([]);
    try {
      data = await api.getProject(projectId);
    } catch (err) {
      setStatus(err.message || "Failed to load project.");
      return;
    }

    setProject(data);
    setExported(asExportItems(data.clips));

    if (Array.isArray(data.draft_clips) && data.draft_clips.length > 0) {
      const restored = enrichClips(data.draft_clips).map((clip) => ({
        ...clip,
        track_id: typeof clip.track_id === "string" ? clip.track_id : DEFAULT_TRACKS[0],
      }));
      setClips(restored);
      setSelectedClipIds(restored[0] ? [restored[0].id] : []);
      setActiveClipId(restored[0]?.id || "");
      setPhase("review");
    }

    if (Array.isArray(data.markers)) {
      setMarkers(data.markers.map((m) => Number(m)).filter((m) => Number.isFinite(m)));
    }

    if (typeof data.selector === "string") setSelector(data.selector);
    if (data.count !== undefined && data.count !== null) setCount(String(data.count));
    if (Array.isArray(data.track_order) && data.track_order.length > 0) {
      const clean = data.track_order.map((t) => String(t)).filter(Boolean);
      if (clean.length) setTrackOrder(clean);
    }

    if (data.zoom !== undefined && data.zoom !== null) {
      const z = Number(data.zoom);
      if (Number.isFinite(z) && z > 0) setZoom(z);
    }

    setIsHydrated(true);
  };

  useEffect(() => {
    loadProject();
  }, [projectId]);

  useEffect(() => {
    if (!project?.id) return;
    let cancelled = false;
    api
      .ensureProjectThumbnails(project.id, false, 600)
      .then((data) => {
        if (cancelled) return;
        const items = Array.isArray(data?.frames) ? data.frames : [];
        const mapped = items
          .map((f) => ({ t: Number(f.t) || 0, src: String(f.src || "") }))
          .filter((f) => f.src);
        if (mapped.length) {
          setServerFrames(mapped);
        }
        // Existing projects may have old low-density thumbnail cache.
        if (mapped.length < 360) {
          api
            .ensureProjectThumbnails(project.id, true, 600)
            .then((next) => {
              if (cancelled) return;
              const refreshed = (Array.isArray(next?.frames) ? next.frames : [])
                .map((f) => ({ t: Number(f.t) || 0, src: String(f.src || "") }))
                .filter((f) => f.src);
              if (refreshed.length) setServerFrames(refreshed);
            })
            .catch(() => {});
        }
      })
      .catch(() => {
        // Fallback to browser frames when backend thumbnails are unavailable.
      });
    return () => {
      cancelled = true;
    };
  }, [project?.id]);

  useEffect(() => {
    if (!dragState) return undefined;

    const onMove = (event) => {
      if (!timelineViewportRef.current || !duration) return;
      const rect = timelineViewportRef.current.getBoundingClientRect();
      const x = event.clientX - rect.left + timelineViewportRef.current.scrollLeft;
      const at = clamp(x / pxPerSec, 0, duration);
      const y = event.clientY - rect.top;
      dragDirtyRef.current = true;

      setClips((prev) =>
        prev.map((clip) => {
          if (clip.id !== dragState.id) return clip;
          if (dragState.mode === "start") {
            return { ...clip, start: clamp(at, 0, clip.end - MIN_CLIP_SEC) };
          }
          if (dragState.mode === "end") {
            return { ...clip, end: clamp(at, clip.start + MIN_CLIP_SEC, duration) };
          }
          if (dragState.mode === "move") {
            const clipDuration = dragState.durationSec;
            const nextStart = clamp(at - dragState.offsetSec, 0, Math.max(0, duration - clipDuration));
            const nextEnd = nextStart + clipDuration;
            const trackBandTop = RULER_HEIGHT + FRAMES_HEIGHT;
            const rawTrackIndex = Math.floor((y - trackBandTop) / TRACK_HEIGHT);
            const safeTrackIndex = clamp(rawTrackIndex, 0, Math.max(0, trackOrder.length - 1));
            const nextTrack = trackOrder[safeTrackIndex] || trackOrder[0] || DEFAULT_TRACKS[0];
            return { ...clip, start: nextStart, end: nextEnd, track_id: nextTrack };
          }
          return clip;
        })
      );
    };

    const onUp = () => {
      if (dragDirtyRef.current) {
        dragDirtyRef.current = false;
        markDirty();
      }
      setDragState(null);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);

    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragState, duration, pxPerSec, trackOrder]);

  const setZoomAt = (nextZoom, anchorClientX = null) => {
    const el = timelineViewportRef.current;
    const clamped = clamp(nextZoom, minZoom, MAX_ZOOM);
    if (clamped === zoom) return;

    if (!el) {
      setZoom(clamped);
      markDirty();
      return;
    }

    const prevPxPerSec = BASE_PX_PER_SEC * zoom;
    const nextPxPerSec = BASE_PX_PER_SEC * clamped;
    const rect = el.getBoundingClientRect();
    const anchorX = anchorClientX === null ? el.clientWidth / 2 : anchorClientX - rect.left;
    const anchorSec = (el.scrollLeft + anchorX) / prevPxPerSec;
    const nearLeft = el.scrollLeft <= 2;
    const nearRight = el.scrollWidth - el.clientWidth - el.scrollLeft <= 2;

    setZoom(clamped);
    markDirty();

    requestAnimationFrame(() => {
      const nextTimelineWidth = Math.max(900, duration * nextPxPerSec);
      const maxScroll = Math.max(0, nextTimelineWidth - el.clientWidth);
      let targetScrollLeft = anchorSec * nextPxPerSec - anchorX;

      // If user is near the left bound, keep zero pinned while zooming in.
      if (nearLeft && (anchorClientX === null || anchorX <= el.clientWidth * 0.7)) {
        targetScrollLeft = 0;
      }
      // Symmetric behavior near the right bound.
      if (nearRight && (anchorClientX === null || anchorX >= el.clientWidth * 0.3)) {
        targetScrollLeft = maxScroll;
      }

      el.scrollLeft = clamp(targetScrollLeft, 0, maxScroll);
      setTimelineView({ left: el.scrollLeft || 0, width: el.clientWidth || 0 });
    });
  };

  useEffect(() => {
    const updateViewport = () => {
      const el = timelineViewportRef.current;
      if (!el) return;
      setTimelineView({ left: el.scrollLeft || 0, width: el.clientWidth || 0 });
    };
    updateViewport();
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  useEffect(() => {
    if (zoom < minZoom) setZoom(minZoom);
    if (zoom > MAX_ZOOM) setZoom(MAX_ZOOM);
  }, [zoom, minZoom]);

  const saveProjectState = async (
    clipsState = clips,
    markersState = markers,
    selectorState = selector,
    countState = count,
    zoomState = zoom,
    withStatus = true
  ) => {
    if (!project?.id) return false;

    setIsProjectSaving(true);
    if (withStatus) setStatus("Saving project...");

    try {
      const payload = {
        project_id: project.id,
        draft_clips: clipsState.map((c) => ({
          id: c.id,
          start: c.start,
          end: c.end,
          track_id: c.track_id || DEFAULT_TRACKS[0],
          text: c.text || "",
          reason: c.reason || "",
          kept: c.kept !== false,
          score: c.score,
        })),
        track_order: trackOrder,
        markers: markersState,
        selector: selectorState,
        count: Number.parseInt(countState, 10) || 8,
        zoom: zoomState,
      };

      await api.saveProject(payload);
      setAutosaveError("");
      if (withStatus) setStatus("Project saved.");
      setIsProjectSaving(false);
      return true;
    } catch (err) {
      setAutosaveError(err.message || "Autosave failed.");
      if (withStatus) setStatus(`Failed to save project: ${err.message || "network error"}`);
      setIsProjectSaving(false);
      return false;
    }
  };

  useEffect(() => {
    if (!isHydrated || !project?.id) return undefined;

    if (dirtyTimeoutRef.current) clearTimeout(dirtyTimeoutRef.current);
    dirtyTimeoutRef.current = setTimeout(() => {
      saveProjectState(clips, markers, selector, count, zoom, false);
    }, 700);

    return () => {
      if (dirtyTimeoutRef.current) clearTimeout(dirtyTimeoutRef.current);
    };
  }, [dirtyVersion, isHydrated, project?.id]);

  useEffect(() => {
    const onKeyDown = (e) => {
      const target = e.target;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;

      if (e.code === "Space") {
        e.preventDefault();
        playPause();
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "0") {
        e.preventDefault();
        setZoomAt(minZoom);
        return;
      }

      if ((e.ctrlKey || e.metaKey) && (e.key === "=" || e.key === "+")) {
        e.preventDefault();
        setZoomAt(zoom * 1.1);
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "-") {
        e.preventDefault();
        setZoomAt(zoom / 1.1);
        return;
      }

      if (e.key === "ArrowRight") {
        e.preventDefault();
        seek(currentTime + (e.shiftKey ? 5 : 1));
        return;
      }

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        seek(currentTime - (e.shiftKey ? 5 : 1));
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [currentTime, minZoom, zoom]);

  const analyze = async () => {
    if (!project?.transcript_path) {
      setStatus("Transcript path is missing.");
      return;
    }

    setIsAnalyzing(true);
    setStatus("Finding interesting moments...");

    let data;
    try {
      data = await api.analyze({
        transcript: project.transcript_path,
        selector,
        count: Number.parseInt(count, 10) || 8,
      });
    } catch (err) {
      setIsAnalyzing(false);
      setStatus(err.message || "Analyze failed.");
      return;
    }

    setIsAnalyzing(false);

    const selected = enrichClips(data.clips).map((clip) => ({
      ...clip,
      track_id: typeof clip.track_id === "string" ? clip.track_id : DEFAULT_TRACKS[0],
    }));
    setClips(selected);
    setSelectedClipIds(selected[0] ? [selected[0].id] : []);
    setActiveClipId(selected[0]?.id || "");
    setPhase("review");
    setStatus(`Generated ${selected.length} clip candidates. Edit and save.`);
    markDirty();
  };

  const saveClips = async () => {
    if (!project?.video_path) {
      setStatus("Video path not found.");
      return;
    }

    if (!keptClips.length) {
      setStatus("No clips selected for export.");
      return;
    }

    setIsSaving(true);
    setStatus("Exporting clips...");

    const payload = {
      project_id: project.id,
      video: project.video_path,
      clips: keptClips.map((clip) => ({
        start: clip.start,
        end: clip.end,
        text: clip.text || "",
        reason: clip.reason || "selected",
      })),
    };

    let data;
    try {
      data = await api.exportClips(payload);
    } catch (err) {
      setIsSaving(false);
      setStatus(err.message || "Export failed.");
      return;
    }

    setIsSaving(false);

    const items = (data.files || []).map((file) => ({
      file,
      url: `${data.base || "/clips/"}${file}`,
      preview_url: `${data.base || "/clips/"}${file}`,
    }));

    setExported(items);
    setPhase("export");
    setStatus(`Saved ${data.files?.length || 0} clips.`);
    await saveProjectState(clips, markers, selector, count, zoom, false);
  };

  const seek = (sec) => {
    if (!videoRef.current) return;
    const target = Math.max(0, sec);
    if (duration > 0) {
      videoRef.current.currentTime = clamp(target, 0, duration);
      return;
    }
    // If metadata is unavailable yet, still try to seek and reflect intent in UI.
    setCurrentTime(target);
    try {
      videoRef.current.currentTime = target;
    } catch {
      // Ignore seek errors until media metadata is ready.
    }
  };

  const startScrub = (event) => {
    if (!timelineViewportRef.current) return;
    event.preventDefault();
    event.stopPropagation();
    setIsScrubbing(true);

    const updateFromClientX = (clientX) => {
      const el = timelineViewportRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const x = clientX - rect.left + el.scrollLeft;
      const maxSec = duration > 0 ? duration : timelineWidth / Math.max(pxPerSec, 0.001);
      const sec = clamp(x / pxPerSec, 0, maxSec);
      setCurrentTime(sec);
      if (videoRef.current) {
        try {
          videoRef.current.currentTime = sec;
        } catch {
          // Ignore seek errors while metadata is not ready.
        }
      }
    };

    updateFromClientX(event.clientX);

    const onMove = (moveEvent) => updateFromClientX(moveEvent.clientX);
    const onUp = () => {
      setIsScrubbing(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const playPause = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      const playPromise = videoRef.current.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch((err) => {
          const text = String(err?.message || "");
          if (text.includes("supported sources") || text.includes("NotSupportedError")) {
            setMediaUnsupported(true);
            setStatus("Browser cannot play this codec. Re-encode to H.264/AAC for in-app preview.");
            if (!isRecoveringPreview && project?.id) {
              recoverPreview();
            }
            return;
          }
          setStatus(`Playback failed: ${text || "unknown error"}`);
        });
      }
      return;
    }
    videoRef.current.pause();
  };

  const recoverPreview = async () => {
    if (!project?.id || isRecoveringPreview) return;
    setIsRecoveringPreview(true);
    setStatus("Preparing browser-compatible preview...");
    try {
      const data = await api.ensureProjectPreview(project.id, true);
      if (data.video_url) {
        setProject((prev) => (prev ? { ...prev, video_url: data.video_url } : prev));
        setMediaUnsupported(false);
        setStatus("Preview updated. Try playback again.");
      } else {
        setStatus("Preview conversion unavailable for this source.");
      }
    } catch (err) {
      setStatus(`Preview conversion failed: ${err.message || "unknown error"}`);
    } finally {
      setIsRecoveringPreview(false);
    }
  };

  const updateClip = (clipId, patch) => {
    setClips((prev) => prev.map((clip) => (clip.id === clipId ? { ...clip, ...patch } : clip)));
    markDirty();
  };

  const toggleKeep = (clipId) => {
    setClips((prev) =>
      prev.map((clip) => (clip.id === clipId ? { ...clip, kept: clip.kept === false } : clip))
    );
    markDirty();
  };

  const addMarker = () => {
    const next = [...markers, currentTime].sort((a, b) => a - b);
    setMarkers(next);
    markDirty();
  };

  const deleteActiveClip = () => {
    const targets = selectedClipIds.length ? new Set(selectedClipIds) : activeClip ? new Set([activeClip.id]) : null;
    if (!targets || targets.size === 0) return;
    const next = clips.filter((clip) => !targets.has(clip.id));
    setClips(next);
    setSelectedClipIds(next[0] ? [next[0].id] : []);
    setActiveClipId(next[0]?.id || "");
    markDirty();
  };

  const splitActiveAtPlayhead = () => {
    if (!activeClip) return;
    if (currentTime <= activeClip.start + MIN_CLIP_SEC || currentTime >= activeClip.end - MIN_CLIP_SEC) {
      setStatus("Move playhead inside the clip to split.");
      return;
    }

    const left = { ...activeClip, end: currentTime };
    const right = { ...activeClip, id: `${activeClip.id}-split-${Date.now()}`, start: currentTime };
    const next = clips.flatMap((clip) => {
      if (clip.id !== activeClip.id) return [clip];
      return [{ ...left, track_id: activeClip.track_id || DEFAULT_TRACKS[0] }, { ...right, track_id: activeClip.track_id || DEFAULT_TRACKS[0] }];
    });

    setClips(next);
    setSelectedClipIds([right.id]);
    setActiveClipId(right.id);
    markDirty();
  };

  const rulerTicks = useMemo(() => {
    if (!duration) return [];
    const targetPx = 180;
    const rough = targetPx / Math.max(pxPerSec, 0.001);
    const candidates = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800];
    const stepSec = candidates.find((v) => v >= rough) || 3600;
    const result = [];
    for (let t = 0; t <= duration; t += stepSec) result.push(t);
    return result;
  }, [duration, pxPerSec]);

  const timelineClips = useMemo(
    () =>
      clips.map((clip) => ({
        ...clip,
        track_id: clip.track_id || DEFAULT_TRACKS[0],
        left: clip.start * pxPerSec,
        width: Math.max(40, (clip.end - clip.start) * pxPerSec),
      })),
    [clips, pxPerSec]
  );

  const clipsByTrack = useMemo(() => {
    const map = new Map(trackOrder.map((t) => [t, []]));
    for (const clip of timelineClips) {
      const key = map.has(clip.track_id) ? clip.track_id : trackOrder[0];
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(clip);
    }
    for (const t of trackOrder) {
      map.get(t).sort((a, b) => a.start - b.start);
    }
    return map;
  }, [timelineClips, trackOrder]);

  const moveTrack = (trackId, dir) => {
    setTrackOrder((prev) => {
      const idx = prev.indexOf(trackId);
      if (idx < 0) return prev;
      const nextIdx = clamp(idx + dir, 0, prev.length - 1);
      if (idx === nextIdx) return prev;
      const next = [...prev];
      const [item] = next.splice(idx, 1);
      next.splice(nextIdx, 0, item);
      markDirty();
      return next;
    });
  };

  const onClipSelect = (event, clip) => {
    const multi = event.metaKey || event.ctrlKey;
    if (multi) {
      setSelectedClipIds((prev) => {
        const set = new Set(prev);
        if (set.has(clip.id)) set.delete(clip.id);
        else set.add(clip.id);
        const arr = [...set];
        if (arr.length) setActiveClipId(arr[arr.length - 1]);
        else setActiveClipId("");
        return arr;
      });
      return;
    }
    setSelectedClipIds([clip.id]);
    setActiveClipId(clip.id);
    seek(clip.start);
  };

  const timelineFrameTiles = useMemo(() => {
    if (!duration || !sortedFrames.length || !pxPerSec) return [];
    const viewportWidth = timelineView.width || timelineViewportWidth || 0;
    const scrollLeft = timelineView.left || 0;
    const startX = Math.max(0, scrollLeft - FRAME_TILE_BUFFER * FRAME_TILE_WIDTH);
    const endX = Math.min(timelineWidth, scrollLeft + viewportWidth + FRAME_TILE_BUFFER * FRAME_TILE_WIDTH);
    const startIdx = Math.max(0, Math.floor(startX / FRAME_TILE_WIDTH));
    const endIdx = Math.max(startIdx, Math.ceil(endX / FRAME_TILE_WIDTH));

    const nearestFrameSrc = (sec) => {
      let lo = 0;
      let hi = sortedFrames.length - 1;
      while (lo < hi) {
        const mid = Math.floor((lo + hi) / 2);
        if (sortedFrames[mid].t < sec) lo = mid + 1;
        else hi = mid;
      }
      const right = lo;
      const left = Math.max(0, right - 1);
      const leftDt = Math.abs((sortedFrames[left]?.t || 0) - sec);
      const rightDt = Math.abs((sortedFrames[right]?.t || 0) - sec);
      return rightDt < leftDt ? sortedFrames[right]?.src || "" : sortedFrames[left]?.src || "";
    };

    const tiles = [];
    for (let idx = startIdx; idx <= endIdx; idx += 1) {
      const left = idx * FRAME_TILE_WIDTH;
      const width = Math.max(1, Math.min(FRAME_TILE_WIDTH, timelineWidth - left));
      if (width <= 0) continue;
      const centerSec = clamp((left + width / 2) / pxPerSec, 0, duration);
      const src = nearestFrameSrc(centerSec);
      if (!src) continue;
      tiles.push({ key: `frame-${idx}`, left, width, src });
    }
    return tiles;
  }, [duration, pxPerSec, sortedFrames, timelineView.left, timelineView.width, timelineViewportWidth, timelineWidth]);

  return (
    <div className="editor-page nle-page">
      <header className="nle-topbar">
        <div className="nle-brand">
          <strong>Smart Clipper Studio</strong>
          <span>{project?.name || "New project"}</span>
        </div>
        <PhaseStepper phase={phase} onChange={setPhase} />
        <div className="nle-header-actions">
          <button className="btn secondary" onClick={analyze} disabled={isAnalyzing}>
            {isAnalyzing ? "Analyzing..." : "Find clips"}
          </button>
          <button className="btn primary" onClick={saveClips} disabled={isSaving || keptClips.length === 0}>
            {isSaving ? "Saving..." : "Export clips"}
          </button>
          <button className="btn secondary" onClick={() => saveProjectState()} disabled={isProjectSaving}>
            {isProjectSaving ? "Saving..." : "Save project"}
          </button>
          <Link to="/" className="back-link">
            Projects
          </Link>
        </div>
      </header>

      <main className="nle-layout">
        <aside className="nle-tools card">
          <h3>Tools</h3>
          <button className="tool-btn active">Media</button>
          <button className="tool-btn">Subtitles</button>
          <button className="tool-btn">Audio</button>
          <button className="tool-btn">Effects</button>
          <button className="tool-btn">Transitions</button>
          <button className="tool-btn">Color</button>
          <button className="tool-btn">Templates</button>
        </aside>

        <section className="nle-main">
          <div className="card nle-preview-card">
            <div className="nle-preview-stage">
              {project?.video_url ? (
                <video
                  key={project.video_url || "video"}
                  ref={videoRef}
                  src={project.video_url}
                  controls
                  onLoadedMetadata={(e) => {
                    setDuration(e.currentTarget.duration || 0);
                    setMediaUnsupported(false);
                  }}
                  onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime || 0)}
                  onError={() => {
                    setMediaUnsupported(true);
                    setStatus("Failed to decode video in browser preview. Try another source or re-encode.");
                  }}
                />
              ) : (
                <div className="video-placeholder">Loading video...</div>
              )}
            </div>

            <div className="nle-transport">
              <div className="nle-transport-left">
                <button onClick={() => seek(currentTime - 5)}>-5s</button>
                <button onClick={playPause}>Play/Pause</button>
                <button onClick={() => seek(currentTime + 5)}>+5s</button>
                <button onClick={addMarker}>Add marker</button>
                <button onClick={splitActiveAtPlayhead}>Split clip</button>
                <button onClick={deleteActiveClip}>Delete clip</button>
              </div>
              <span className="timecode">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
          </div>

          <div className="card nle-timeline-card">
            <div className="nle-timeline-toolbar">
              <select
                value={selector}
                onChange={(e) => {
                  setSelector(e.target.value);
                  markDirty();
                }}
              >
                <option value="both">both</option>
                <option value="llm">llm</option>
                <option value="heuristic">heuristic</option>
              </select>

              <input
                value={count}
                onChange={(e) => {
                  setCount(e.target.value);
                  markDirty();
                }}
                placeholder="clips count"
              />

              <button className="btn secondary" type="button" onClick={() => setZoomAt(minZoom)} title="Fit full video">
                Fit
              </button>

              <label className="zoom">
                Zoom ({Math.max(visibleWindowSec, 0.1).toFixed(1)}s)
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={zoomSlider}
                  onChange={(e) => {
                    const p = clamp(Number(e.target.value) / 100, 0, 1);
                    const next = Math.exp(Math.log(minZoom) + p * (Math.log(MAX_ZOOM) - Math.log(minZoom)));
                    setZoomAt(next);
                  }}
                />
              </label>
            </div>

            <div className="nle-timeline-shell">
              <div className="nle-track-headers">
                <div className="track-label ruler-label">Time</div>
                <div className="track-label">Video frames</div>
                {trackOrder.map((trackId) => (
                  <div key={`hdr-${trackId}`} className="track-label track-head">
                    <span>{trackId}</span>
                    <div className="track-head-actions">
                      <button type="button" onClick={() => moveTrack(trackId, -1)} title="Move up">
                        ↑
                      </button>
                      <button type="button" onClick={() => moveTrack(trackId, 1)} title="Move down">
                        ↓
                      </button>
                    </div>
                  </div>
                ))}
                <div className="track-label">Markers</div>
              </div>

              <div
                className={`timeline-viewport ${isScrubbing ? "scrubbing" : ""}`}
                ref={timelineViewportRef}
                onWheel={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const el = timelineViewportRef.current;
                  if (!el) return;
                  if (e.shiftKey) {
                    const pan = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
                    el.scrollLeft += pan;
                    setTimelineView({
                      left: el.scrollLeft || 0,
                      width: el.clientWidth || 0,
                    });
                    return;
                  }
                  const delta = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
                  const scale = Math.exp(-delta * 0.0018);
                  setZoomAt(zoom * scale, e.clientX);
                }}
                onScroll={(e) =>
                  setTimelineView({
                    left: e.currentTarget.scrollLeft || 0,
                    width: e.currentTarget.clientWidth || 0,
                  })
                }
              >
                <div
                  className="timeline-content"
                  style={{ width: `${timelineWidth}px`, height: `${timelineHeight}px` }}
                  onMouseDown={(e) => {
                    if (e.button !== 0) return;
                    const blocked = e.target.closest(".clip-block, .handle, .marker");
                    if (blocked) return;
                    startScrub(e);
                  }}
                >
                  <div className="ruler">
                    {rulerTicks.map((t) => (
                      <div key={`tick-${t}`} className="tick" style={{ left: `${t * pxPerSec}px` }}>
                        <span>{formatTime(t)}</span>
                      </div>
                    ))}
                  </div>

                  <div className="track-row frames-row">
                    {timelineFrameTiles.map((tile) => (
                      <div key={tile.key} className="frame-tile" style={{ left: `${tile.left}px`, width: `${tile.width}px` }}>
                        <img src={tile.src} alt="" draggable={false} loading="eager" />
                      </div>
                    ))}
                  </div>

                  {trackOrder.map((trackId, idx) => (
                    <div
                      key={`track-${trackId}`}
                      className="track-row clip-row"
                      style={{ top: `${RULER_HEIGHT + FRAMES_HEIGHT + idx * TRACK_HEIGHT}px` }}
                    >
                      {(clipsByTrack.get(trackId) || []).map((clip) => (
                        <div
                          key={clip.id}
                          className={`clip-block ${clip.id === activeClipId ? "active" : ""} ${
                            clip.kept === false ? "discarded" : ""
                          } ${selectedSet.has(clip.id) ? "selected" : ""}`}
                          style={{ left: `${clip.left}px`, width: `${clip.width}px` }}
                          onMouseDown={(e) => {
                            if (e.target.closest(".handle")) return;
                            const rect = timelineViewportRef.current?.getBoundingClientRect();
                            if (!rect) return;
                            const x = e.clientX - rect.left + (timelineViewportRef.current?.scrollLeft || 0);
                            const at = clamp(x / pxPerSec, 0, duration);
                            dragDirtyRef.current = false;
                            setDragState({
                              id: clip.id,
                              mode: "move",
                              offsetSec: at - clip.start,
                              durationSec: clip.end - clip.start,
                            });
                          }}
                          onClick={(e) => onClipSelect(e, clip)}
                        >
                          <span
                            className="handle start"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              dragDirtyRef.current = false;
                              setDragState({ id: clip.id, mode: "start" });
                            }}
                          />
                          <span className="title">
                            {formatTime(clip.start)} - {formatTime(clip.end)}
                          </span>
                          <span
                            className="handle end"
                            onMouseDown={(e) => {
                              e.stopPropagation();
                              dragDirtyRef.current = false;
                              setDragState({ id: clip.id, mode: "end" });
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  ))}

                  <div className="markers-row" style={{ top: `${RULER_HEIGHT + FRAMES_HEIGHT + trackOrder.length * TRACK_HEIGHT}px` }}>
                    {markers.map((m, idx) => (
                      <div key={`marker-${idx}-${m}`} className="marker" style={{ left: `${m * pxPerSec}px` }} />
                    ))}
                  </div>

                  <div className="playhead" style={{ left: `${currentTime * pxPerSec}px` }} onMouseDown={startScrub} />
                </div>
              </div>
            </div>
          </div>

          <div className="nle-status-row">
            <div className="status-line">{status}</div>
            {!!autosaveError && <div className="status-line status-error">Autosave error: {autosaveError}</div>}
            {mediaUnsupported && (
              <div className="status-line status-error">
                Preview codec unsupported.
                <button type="button" className="mini-btn keep" onClick={recoverPreview} disabled={isRecoveringPreview}>
                  {isRecoveringPreview ? "Converting..." : "Fix preview"}
                </button>
              </div>
            )}
          </div>
        </section>

        <aside className="nle-inspector card">
          <div className="inspector">
            <h3>Inspector</h3>
            {!activeClip && <div className="empty-card">Select clip</div>}
            {activeClip && (
              <div className="inspector-form">
                <label>Start</label>
                <input
                  type="number"
                  step="0.1"
                  value={activeClip.start}
                  onChange={(e) =>
                    updateClip(activeClip.id, {
                      start: clamp(Number(e.target.value), 0, activeClip.end - MIN_CLIP_SEC),
                    })
                  }
                />
                <label>End</label>
                <input
                  type="number"
                  step="0.1"
                  value={activeClip.end}
                  onChange={(e) =>
                    updateClip(activeClip.id, {
                      end: clamp(Number(e.target.value), activeClip.start + MIN_CLIP_SEC, duration || activeClip.end),
                    })
                  }
                />
                <label>Reason</label>
                <input
                  value={activeClip.reason || ""}
                  onChange={(e) => updateClip(activeClip.id, { reason: e.target.value })}
                  placeholder="Why this clip matters"
                />
                <label>Duration</label>
                <div className="readonly">{(activeClip.end - activeClip.start).toFixed(2)}s</div>
                <label>Set duration</label>
                <input
                  type="number"
                  step="0.1"
                  min={MIN_CLIP_SEC}
                  value={(activeClip.end - activeClip.start).toFixed(1)}
                  onChange={(e) => {
                    const d = Math.max(MIN_CLIP_SEC, Number(e.target.value) || MIN_CLIP_SEC);
                    updateClip(activeClip.id, {
                      end: clamp(activeClip.start + d, activeClip.start + MIN_CLIP_SEC, duration || activeClip.start + d),
                    });
                  }}
                />
                <button
                  className={`btn ${activeClip.kept === false ? "secondary" : "success"}`}
                  onClick={() => toggleKeep(activeClip.id)}
                >
                  {activeClip.kept === false ? "Mark as keep" : "Keep in export"}
                </button>
              </div>
            )}
          </div>

          <div className="inspector-summary">
            <div className="summary-item">
              <span>Clips found</span>
              <strong>{clips.length}</strong>
            </div>
            <div className="summary-item">
              <span>Keep for export</span>
              <strong>{keptClips.length}</strong>
            </div>
            <div className="summary-item">
              <span>Exported</span>
              <strong>{exported.length}</strong>
            </div>
          </div>

          <div className="card nle-panel-list">
            <h4>Candidates</h4>
            {clips.length === 0 && <div className="empty-card">No clip candidates yet.</div>}
            {clips.map((clip) => (
              <button
                key={clip.id}
                className={`clip-mini ${clip.id === activeClipId ? "active" : ""}`}
                onClick={(e) => {
                  onClipSelect(e, clip);
                  seek(clip.start);
                  setPhase("review");
                }}
              >
                <span>{formatTime(clip.start)} - {formatTime(clip.end)}</span>
                <small>{clip.reason || "Candidate"}</small>
              </button>
            ))}
          </div>

          <div className="card nle-panel-list">
            <h4>Exported clips</h4>
            {exported.length === 0 && <div className="empty-card">No exported clips yet.</div>}
            {exported.map((clip) => (
              <article key={clip.url} className="saved-card">
                <video src={clip.preview_url || clip.url} controls preload="metadata" />
                <a href={clip.url} className="video-link">
                  {clip.file}
                </a>
              </article>
            ))}
          </div>
        </aside>
      </main>
    </div>
  );
}
