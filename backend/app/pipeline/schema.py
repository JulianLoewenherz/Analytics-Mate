"""
Pydantic schema for the analysis plan.

Validates plan JSON from the LLM or from the client before execution.
Rejects unknown tasks, invalid types, and extra fields.

Spec: PIPELINE-LOGIC.md Section 2, 5.5.
"""

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TaskName(str, Enum):
    """Registered task names. Only implemented tasks are included."""
    dwell_count = "dwell_count"
    # Phase 3: traffic_count, occupancy, count_per_interval, exit_reentry
    # Phase 4: pose_event_count, object_co_occurrence_dwell


class AppearanceFilter(BaseModel):
    """Color-based filter on track crops. Phase 4."""
    color_region: Literal["torso", "full", "lower", "upper"] = "torso"
    color: str


class ObjectAssociation(BaseModel):
    """Associate primary object with secondary (e.g. person at table). Phase 4."""
    associate_with: str  # YOLO class name
    method: Literal["bbox_overlap", "proximity", "containment"] = "bbox_overlap"
    max_distance_px: Optional[int] = 50


class VisionConfig(BaseModel):
    """YOLO vision configuration."""
    model: str = "yolo11n.pt"
    enable_tracking: bool = True
    enable_pose: bool = False
    detect_classes: list[str] = Field(default_factory=lambda: ["person"])
    sample_fps: Optional[float] = None
    confidence_threshold: float = 0.4


class Filters(BaseModel):
    """Filter configuration: ROI mode, appearance, object association, quality."""
    roi_mode: Literal["inside", "enters", "crosses", "outside"] = "inside"
    appearance: Optional[AppearanceFilter] = None
    object_association: Optional[ObjectAssociation] = None
    min_track_frames: int = 5
    min_confidence: float = 0.4


class OutputConfig(BaseModel):
    """Output configuration: what to include in the result."""
    include_events: bool = True
    include_aggregates: bool = True
    include_annotated_frames: bool = False
    include_timeline: bool = True


class AnalysisPlan(BaseModel):
    """
    Full analysis plan schema.
    Must match what the LLM produces and what the pipeline runner expects.
    """
    task: TaskName
    object: str = "person"
    use_roi: bool = True
    vision: VisionConfig = Field(default_factory=VisionConfig)
    filters: Filters = Field(default_factory=Filters)
    params: dict = Field(default_factory=dict)
    output: OutputConfig = Field(default_factory=OutputConfig)
    explanation: Optional[str] = None
    roi_instruction: Optional[str] = None  # e.g. "Draw an ROI on the crosswalk"

    def to_plan_dict(self) -> dict:
        """Convert to dict for the pipeline runner (excludes explanation)."""
        d = self.model_dump(exclude={"explanation"})
        d["task"] = self.task.value  # Ensure task is string, not enum
        return d
