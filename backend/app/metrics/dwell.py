"""
Dwell count metric.

For each track, compute how long its center point stays inside the ROI.
Emit events for tracks that dwell >= threshold.

Spec: PIPELINE-LOGIC.md Section 8.1.
"""

import logging
from statistics import mean

from shapely.geometry import Point, Polygon

from app.vision.models import Track

logger = logging.getLogger(__name__)


def _find_contiguous_runs(frame_indices: list[int]) -> list[tuple[int, int]]:
    """
    Find contiguous runs in a sorted list of frame indices.

    A "run" is a sequence of frame indices where each consecutive pair differs
    by at most a small gap (we allow gap of 1 — i.e. consecutive frames).

    Returns list of (start_frame, end_frame) tuples.
    """
    if not frame_indices:
        return []

    runs = []
    run_start = frame_indices[0]
    prev = frame_indices[0]

    for idx in frame_indices[1:]:
        # Allow a gap of up to 2 frames (accounts for occasional missed detections)
        if idx - prev <= 2:
            prev = idx
        else:
            runs.append((run_start, prev))
            run_start = idx
            prev = idx

    # Don't forget the last run
    runs.append((run_start, prev))
    return runs


def compute_dwell_count(
    tracks: list[Track],
    params: dict,
    roi_polygon: list[dict] | None,
    fps: float,
    video_duration: float,
) -> dict:
    """
    Compute dwell events for tracks inside an ROI.

    For each track, check which detections have their bbox center inside the ROI
    polygon. Find contiguous runs of "inside" frames. Emit dwell events for runs
    where duration >= threshold.

    Args:
        tracks: Filtered tracks (already ROI-filtered by the pipeline runner,
                but we re-check against the polygon here for precise per-frame timing).
        params: Task-specific parameters:
            - dwell_threshold_seconds (float, default 5.0): Min seconds to count as dwelling.
            - jitter_tolerance_px (int, default 15): Future — ignore brief exits near edge.
        roi_polygon: List of {"x": float, "y": float} points defining the ROI.
                     If None, all detections are considered "inside".
        fps: Video frames per second.
        video_duration: Total video duration in seconds.

    Returns:
        Dict with "events" and "aggregates" keys.
    """
    threshold = params.get("dwell_threshold_seconds", 5.0)
    # jitter_tolerance_px = params.get("jitter_tolerance_px", 15)  # Phase 1: not used yet

    # Build Shapely polygon if ROI provided
    polygon = None
    if roi_polygon:
        polygon = Polygon([(p["x"], p["y"]) for p in roi_polygon])
        if not polygon.is_valid:
            logger.warning("ROI polygon is invalid in dwell metric, treating all detections as inside")
            polygon = None

    events = []

    for track in tracks:
        # Determine which frames have the track center inside the ROI
        inside_frames = []
        for det in track.detections:
            center_x, center_y = det.bbox.center
            if polygon is None or polygon.contains(Point(center_x, center_y)):
                inside_frames.append(det.frame_index)

        if not inside_frames:
            continue

        # Find contiguous runs of "inside" frames
        runs = _find_contiguous_runs(inside_frames)

        for run_start, run_end in runs:
            # Duration = number of frames in run / fps
            # We add 1 because both start and end frames are inclusive
            num_frames = run_end - run_start + 1
            duration = num_frames / fps if fps > 0 else 0

            if duration >= threshold:
                events.append({
                    "type": "dwell",
                    "track_id": track.track_id,
                    "start_time_sec": round(run_start / fps, 2) if fps > 0 else 0,
                    "end_time_sec": round(run_end / fps, 2) if fps > 0 else 0,
                    "duration_sec": round(duration, 2),
                    "frame_start": run_start,
                    "frame_end": run_end,
                })

    # Compute aggregates
    if events:
        durations = [e["duration_sec"] for e in events]
        unique_track_ids = set(e["track_id"] for e in events)
        aggregates = {
            "total_dwellers": len(unique_track_ids),
            "total_dwell_events": len(events),
            "average_dwell_seconds": round(mean(durations), 2),
            "max_dwell_seconds": round(max(durations), 2),
            "min_dwell_seconds": round(min(durations), 2),
        }
    else:
        aggregates = {
            "total_dwellers": 0,
            "total_dwell_events": 0,
            "average_dwell_seconds": 0,
            "max_dwell_seconds": 0,
            "min_dwell_seconds": 0,
        }

    logger.info(
        f"dwell_count: threshold={threshold}s, "
        f"{len(events)} events from {aggregates['total_dwellers']} unique tracks"
    )

    return {"events": events, "aggregates": aggregates}
