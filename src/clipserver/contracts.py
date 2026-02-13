from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ClipDraft:
    id: str
    start: float
    end: float
    text: str = ""
    reason: str = ""
    kept: bool = True
    score: Optional[float] = None


@dataclass
class ProjectCreateRequest:
    name: str
    source_url: str
    video_path: str
    transcript_path: str


@dataclass
class ProjectSaveRequest:
    project_id: str
    draft_clips: List[ClipDraft]
    markers: List[float]
    selector: str
    count: int
    zoom: float


@dataclass
class ExportRequest:
    project_id: str
    video: str
    clips: List[ClipDraft]


@dataclass
class AnalyzeRequest:
    transcript: str
    selector: str
    count: int
