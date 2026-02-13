export const MIN_CLIP_SEC = 3;

export const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export const formatTime = (sec) => {
  if (!Number.isFinite(sec)) return "--:--";
  const s = Math.max(0, sec);
  const m = Math.floor(s / 60);
  const r = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${r}`;
};

export const normalizeClips = (items) =>
  (Array.isArray(items) ? items : []).map((item, idx) => ({
    ...item,
    id: item.id || `clip-${idx}`,
    start: Number(item.start || 0),
    end: Number(item.end || 0),
  }));
