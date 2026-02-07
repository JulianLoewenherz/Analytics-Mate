"""
Shared drawing utilities for video visualizers.
"""

import cv2
import numpy as np
from collections import defaultdict

from app.vision.models import Track, Detection


def build_frame_lookup(tracks: list[Track]) -> dict[int, list[Detection]]:
    """Build a dict mapping frame_index → list of Detections in that frame."""
    lookup: dict[int, list[Detection]] = defaultdict(list)
    for track in tracks:
        for det in track.detections:
            lookup[det.frame_index].append(det)
    return lookup


def draw_roi_polygon(
    frame: np.ndarray, roi_points: list[dict], color=(255, 255, 0), thickness=2
) -> None:
    """Draw the ROI polygon on a frame."""
    pts = np.array([(int(p["x"]), int(p["y"])) for p in roi_points], dtype=np.int32)
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=thickness)
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color=(255, 255, 0))
    cv2.addWeighted(overlay, 0.1, frame, 0.9, 0, frame)


def draw_detection(frame: np.ndarray, det: Detection, state: str) -> None:
    """
    Draw a bounding box + track ID on a frame.

    state: "outside" = red (not in ROI), "inside" = yellow (in ROI, not yet qualified),
           "qualified" = green (in ROI and metric requirement met).
    """
    x1, y1, x2, y2 = int(det.bbox.x1), int(det.bbox.y1), int(det.bbox.x2), int(det.bbox.y2)

    if state == "qualified":
        color = (0, 220, 0)  # BGR green
    elif state == "inside":
        color = (0, 255, 255)  # BGR yellow
    else:
        color = (0, 0, 220)  # BGR red (outside)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    label = f"#{det.track_id}"
    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(
        frame,
        (x1, y1 - label_size[1] - 8),
        (x1 + label_size[0] + 4, y1),
        color,
        -1,
    )
    cv2.putText(frame, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cx, cy = int(det.bbox.center[0]), int(det.bbox.center[1])
    cv2.circle(frame, (cx, cy), 4, color, -1)


def draw_info_overlay(
    frame: np.ndarray,
    frame_idx: int,
    timestamp: float,
    fps: float,
    n_detections: int,
    n_inside: int,
    n_qualified: int = 0,
    extra_lines: list[str] | None = None,
) -> None:
    """Draw frame info text in the top-left corner."""
    lines = [
        f"Frame: {frame_idx}  |  Time: {timestamp:.2f}s",
        f"Detections: {n_detections}  |  In ROI: {n_inside}  |  Qualified: {n_qualified}",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    y = 40
    for line in lines:
        cv2.putText(frame, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(frame, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        y += 35
