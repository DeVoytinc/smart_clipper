import { formatTime } from "../editor/utils.js";

export default function ClipList({ clips, activeClipId, onSelect, onToggleKeep }) {
  if (!clips.length) {
    return <div className="empty-card">No clips yet. Run generation first.</div>;
  }

  return (
    <div className="clip-list">
      {clips.map((clip, idx) => (
        <article
          key={clip.id}
          className={`clip-card ${clip.id === activeClipId ? "active" : ""} ${clip.kept ? "" : "discarded"}`}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(clip)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect(clip);
            }
          }}
        >
          <div className="clip-card-row">
            <strong>#{idx + 1}</strong>
            <span className="score">Score {Math.round(Number(clip.score) || 0)}</span>
          </div>
          <div className="clip-time">
            {formatTime(clip.start)} - {formatTime(clip.end)}
          </div>
          <div className="clip-reason">{clip.reason || "Selected by model"}</div>
          <button
            type="button"
            className={`mini-btn ${clip.kept ? "keep" : "discard"}`}
            onClick={(e) => {
              e.stopPropagation();
              onToggleKeep(clip.id);
            }}
          >
            {clip.kept ? "Keep" : "Discarded"}
          </button>
        </article>
      ))}
    </div>
  );
}
