"""
Traffic count visualizer.

Renders annotated video with permanent state progression per track:
- Red    = outside ROI, condition not yet met
- Yellow = inside ROI, condition not yet met
- Green  = condition met (stays green for the rest of the video)

State transitions per mode:
- "enters":  RED → GREEN at the moment of entry (yellow briefly if already inside on first frame)
- "exits":   RED → YELLOW (inside) → GREEN at the moment of exit, stays green outside
- "crosses": RED → YELLOW (inside) → GREEN at the moment of exit (both sides crossed)
"""

import logging
from pathlib import Path

import cv2
from shapely.geometry import Point, Polygon

from app.vision.models import Track, Detection
from app.visualizers.common import (
    build_frame_lookup,
    draw_roi_polygon,
    draw_detection,
    draw_info_overlay,
)

logger = logging.getLogger(__name__)


def _build_qualified_from(events: list[dict], roi_mode: str) -> dict[int, int]:
    """
    Build a mapping of track_id → first frame at which the track is permanently qualified.

    - "enters":  qualified at the entry frame (outside→inside transition)
    - "exits":   qualified at the exit frame (inside→outside transition)
    - "crosses": qualified at the exit frame (must have both entered AND exited)
    """
    qualified_from: dict[int, int] = {}

    for e in events:
        track_id = e.get("track_id")
        event_frame = e.get("frame")
        event_type = e.get("type")
        if track_id is None or event_frame is None:
            continue

        if roi_mode == "enters" and event_type == "entry":
            if track_id not in qualified_from:
                qualified_from[track_id] = event_frame

        elif roi_mode == "exits" and event_type == "exit":
            if track_id not in qualified_from:
                qualified_from[track_id] = event_frame

        elif roi_mode == "crosses" and event_type == "exit":
            # For crosses, the track qualifies at its exit (it must have already entered)
            if track_id not in qualified_from:
                qualified_from[track_id] = event_frame

    return qualified_from


def visualize_traffic(
    *,
    all_tracks: list[Track],
    filtered_tracks: list[Track],
    roi_polygon: list[dict] | None,
    params: dict,
    events: list[dict],
    video_path: str,
    video_id: str,
    fps: float,
    width: int,
    height: int,
    frame_count: int,
    output_dir: Path,
) -> Path | None:
    """
    Render annotated traffic video and return path to the output file.

    Color codes (permanent progression — never reverts):
    - Red:    outside ROI, not yet qualified
    - Yellow: inside ROI, not yet qualified
    - Green:  condition met — stays green for the rest of the video

    Returns None if rendering fails.
    """
    roi_polygon_raw = roi_polygon
    roi_polygon_shapely = None
    if roi_polygon_raw:
        roi_polygon_shapely = Polygon([(p["x"], p["y"]) for p in roi_polygon_raw])

    frame_lookup = build_frame_lookup(all_tracks)

    # Track IDs that survived all filters (ROI + appearance + quality)
    filtered_track_ids: set[int] = {t.track_id for t in filtered_tracks}

    # Derive roi_mode from events — if any exit events present alongside entry events
    # it's "crosses"; if only exits, "exits"; otherwise "enters"
    has_entry = any(e.get("type") == "entry" for e in events)
    has_exit = any(e.get("type") == "exit" for e in events)
    if has_entry and has_exit:
        roi_mode = "crosses"
    elif has_exit:
        roi_mode = "exits"
    else:
        roi_mode = "enters"

    # track_id → first frame at which it's permanently qualified (green)
    qualified_from = _build_qualified_from(events, roi_mode)

    # (track_id, frame_index) → inside ROI (for yellow state)
    inside_roi_pairs: set[tuple[int, int]] = set()
    if roi_polygon_shapely:
        for track in all_tracks:
            for det in track.detections:
                cx, cy = det.bbox.center
                if roi_polygon_shapely.contains(Point(cx, cy)):
                    inside_roi_pairs.add((det.track_id, det.frame_index))
    else:
        # No ROI: only appearance-filtered tracks count as "inside"
        # Non-matched tracks render as "outside" (red) to show they were filtered
        for track in filtered_tracks:
            for det in track.detections:
                inside_roi_pairs.add((det.track_id, det.frame_index))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.mp4"

    try:
        cap = cv2.VideoCapture(str(video_path))
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / fps if fps > 0 else 0

            if roi_polygon_raw:
                draw_roi_polygon(frame, roi_polygon_raw)

            dets_in_frame = frame_lookup.get(frame_idx, [])
            n_inside = 0
            n_qualified = 0

            for det in dets_in_frame:
                qualified_at = qualified_from.get(det.track_id)

                if qualified_at is not None and det.frame_index >= qualified_at:
                    # Permanently green — condition met, never reverts
                    state = "qualified"
                    n_qualified += 1
                elif (det.track_id, det.frame_index) in inside_roi_pairs:
                    # Inside ROI but not yet qualified
                    state = "inside"
                    n_inside += 1
                else:
                    # Outside ROI, not yet qualified
                    state = "outside"

                draw_detection(frame, det, state=state)

            draw_info_overlay(
                frame,
                frame_idx,
                timestamp,
                fps,
                len(dets_in_frame),
                n_inside + n_qualified,
                n_qualified,
                extra_lines=[f"Traffic ({roi_mode}): green = condition met"],
            )

            out.write(frame)
            frame_idx += 1

        cap.release()
        out.release()
        logger.info(f"Traffic visualizer wrote {output_path}")
        return output_path
    except Exception as e:
        logger.exception(f"Traffic visualizer failed: {e}")
        return None
