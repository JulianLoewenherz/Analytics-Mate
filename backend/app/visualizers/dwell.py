"""
Dwell count visualizer.

Renders annotated video with:
- Red = outside ROI
- Yellow = in ROI, not yet dwell qualified
- Green = dwell qualified (>= threshold)
"""

import math
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


def visualize_dwell(
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
    Render annotated dwell video and return path to the output file.

    Returns None if rendering fails.
    """
    threshold = params.get("dwell_threshold_seconds", 5.0)
    roi_polygon_raw = roi_polygon
    roi_polygon_shapely = None
    if roi_polygon_raw:
        roi_polygon_shapely = Polygon([(p["x"], p["y"]) for p in roi_polygon_raw])

    frame_lookup = build_frame_lookup(all_tracks)

    # Track IDs that survived all filters (ROI + appearance + quality)
    filtered_track_ids: set[int] = {t.track_id for t in filtered_tracks}

    # (track_id, frame_index) → inside ROI
    inside_roi_pairs: set[tuple[int, int]] = set()
    if roi_polygon_shapely:
        for track in filtered_tracks:
            for det in track.detections:
                cx, cy = det.bbox.center
                if roi_polygon_shapely.contains(Point(cx, cy)):
                    inside_roi_pairs.add((det.track_id, det.frame_index))
    else:
        # No ROI: only filtered (appearance-matched) tracks count as "inside"
        # Tracks NOT in filtered_tracks render as "outside" (red) to show filtering
        for track in filtered_tracks:
            for det in track.detections:
                inside_roi_pairs.add((det.track_id, det.frame_index))

    # (track_id, frame_index) → dwell qualified
    threshold_frames = math.ceil(threshold * fps) if fps > 0 else 0
    dwell_qualified_pairs: set[tuple[int, int]] = set()
    for e in events:
        first_qualified = e.get("frame_start", 0) + threshold_frames
        frame_end = e.get("frame_end", 0)
        if first_qualified <= frame_end:
            for fi in range(first_qualified, frame_end + 1):
                dwell_qualified_pairs.add((e["track_id"], fi))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id}.mp4"

    try:
        cap = cv2.VideoCapture(str(video_path))
        # Use H.264 (avc1) for browser compatibility; mp4v has poor support in Chrome/Firefox
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
                key = (det.track_id, det.frame_index)
                if key not in inside_roi_pairs:
                    state = "outside"
                elif key in dwell_qualified_pairs:
                    state = "qualified"
                    n_inside += 1
                    n_qualified += 1
                else:
                    state = "inside"
                    n_inside += 1
                draw_detection(frame, det, state=state)

            draw_info_overlay(
                frame, frame_idx, timestamp, fps, len(dets_in_frame), n_inside, n_qualified
            )

            out.write(frame)
            frame_idx += 1

        cap.release()
        out.release()
        logger.info(f"Dwell visualizer wrote {output_path}")
        return output_path
    except Exception as e:
        logger.exception(f"Dwell visualizer failed: {e}")
        return None
