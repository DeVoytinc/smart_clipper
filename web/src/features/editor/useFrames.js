import { useEffect, useState } from "react";

import { clamp } from "./utils.js";

const FRAME_CACHE = new Map();
const EMPTY_FRAME =
  "data:image/gif;base64,R0lGODlhAQABAPAAAMzMzAAAACH5BAAAAAAALAAAAAABAAEAAAICRAEAOw==";

function safeCaptureFrame(ctx, probe, width, height, fallbackSrc) {
  try {
    if (probe.videoWidth > 0 && probe.videoHeight > 0) {
      ctx.drawImage(probe, 0, 0, width, height);
      const encoded = canvasToJpeg(ctx.canvas);
      return encoded && encoded !== EMPTY_FRAME ? encoded : fallbackSrc || EMPTY_FRAME;
    }
  } catch {
    // Ignore draw failures and use fallback.
  }
  return fallbackSrc || EMPTY_FRAME;
}

function canvasToJpeg(canvas) {
  try {
    return canvas.toDataURL("image/jpeg", 0.64);
  } catch {
    return EMPTY_FRAME;
  }
}

async function buildFrames(videoUrl, duration, frameCount) {
  if (!videoUrl || !duration || frameCount < 2) return [];
  const cacheKey = `${videoUrl}|${duration.toFixed(3)}|${frameCount}`;
  if (FRAME_CACHE.has(cacheKey)) {
    return FRAME_CACHE.get(cacheKey);
  }

  const probe = document.createElement("video");
  probe.src = videoUrl;
  probe.crossOrigin = "anonymous";
  probe.preload = "auto";
  probe.muted = true;
  probe.playsInline = true;

  await new Promise((resolve) => {
    const timeoutId = setTimeout(resolve, 5000);
    probe.onloadedmetadata = () => {
      clearTimeout(timeoutId);
      resolve();
    };
    probe.onerror = () => {
      clearTimeout(timeoutId);
      resolve();
    };
  });

  const canvas = document.createElement("canvas");
  const width = 120;
  const height = 68;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const output = [];
  let lastGoodSrc = EMPTY_FRAME;

  async function captureAt(targetSec) {
    return new Promise((resolve) => {
      let settled = false;
      let timeoutId = null;

      const finish = () => {
        if (settled) return;
        settled = true;
        if (timeoutId) clearTimeout(timeoutId);
        const actualSec = clamp(
          Number.isFinite(probe.currentTime) ? probe.currentTime : targetSec,
          0,
          Math.max(0, duration)
        );
        const src = safeCaptureFrame(ctx, probe, width, height, lastGoodSrc);
        if (src && src !== EMPTY_FRAME) lastGoodSrc = src;
        probe.onseeked = null;
        probe.onerror = null;
        resolve({ actualSec, src });
      };

      timeoutId = setTimeout(finish, 2200);
      probe.onseeked = () => finish();
      probe.onerror = () => finish();
      probe.currentTime = clamp(targetSec, 0, Math.max(0, duration - 0.05));
    });
  }

  for (let i = 0; i < frameCount; i += 1) {
    const t = (duration * i) / (frameCount - 1);
    let frame = await captureAt(t);
    // On long videos some browsers return a far frame after a seek.
    // Retry once if drift is significant to improve timeline-time alignment.
    if (Math.abs(frame.actualSec - t) > 1.25) {
      const retry = await captureAt(t);
      if (Math.abs(retry.actualSec - t) < Math.abs(frame.actualSec - t)) frame = retry;
    }
    // Keep timeline spacing stable by target time; store actual seek time for debug only.
    output.push({ t, src: frame.src, actual_t: frame.actualSec });
  }

  probe.removeAttribute("src");
  probe.load();
  FRAME_CACHE.set(cacheKey, output);
  return output;
}

export function useFrames(videoUrl, duration) {
  const [frames, setFrames] = useState([]);

  useEffect(() => {
    if (!videoUrl || !duration) {
      setFrames([]);
      return;
    }
    let cancelled = false;
    // Keep frame sampling stable across zoom changes to avoid timeline flicker.
    // Cap count for long videos so extraction remains responsive.
    const frameCount = clamp(Math.round(duration / 20), 60, 160);
    buildFrames(videoUrl, duration, frameCount).then((items) => {
      if (!cancelled) setFrames(Array.isArray(items) ? items : []);
    });
    return () => {
      cancelled = true;
    };
  }, [videoUrl, duration]);

  return frames;
}
