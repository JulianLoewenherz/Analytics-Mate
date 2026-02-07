"""
Core data models for the vision layer.

These Pydantic models define the data contract between the vision layer
(YOLO detection + tracking) and everything downstream (filters, metrics).
Spec: PIPELINE-LOGIC.md Section 6.5.
"""

from pydantic import BaseModel
from typing import Optional


class BBox(BaseModel):
    """Bounding box in pixel coordinates."""
    x1: float  # top-left x
    y1: float  # top-left y
    x2: float  # bottom-right x
    y2: float  # bottom-right y

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


class Detection(BaseModel):
    """A single detection in a single frame."""
    frame_index: int
    timestamp_sec: float
    bbox: BBox
    class_name: str
    confidence: float
    track_id: Optional[int] = None

    class Config:
        # Allow computed properties on BBox to be accessed
        arbitrary_types_allowed = True


class Track(BaseModel):
    """A tracked object across multiple frames."""
    track_id: int
    class_name: str
    detections: list[Detection]  # sorted by frame_index

    @property
    def start_time(self) -> float:
        return self.detections[0].timestamp_sec if self.detections else 0.0

    @property
    def end_time(self) -> float:
        return self.detections[-1].timestamp_sec if self.detections else 0.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def frame_count(self) -> int:
        return len(self.detections)
