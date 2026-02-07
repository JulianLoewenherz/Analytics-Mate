"""
Track filtering functions.

Each filter is a pure function: tracks in, tracks out.
Filters run in sequence: quality → ROI → (future: appearance, association).

Spec: PIPELINE-LOGIC.md Section 7.3 and Section 9.1.
"""

import logging
from shapely.geometry import Point, Polygon

from app.vision.models import Track, Detection

logger = logging.getLogger(__name__)


def filter_by_min_frames(tracks: list[Track], min_frames: int = 5) -> list[Track]:
    """Drop tracks with fewer than `min_frames` detections (reduces noise)."""
    result = [t for t in tracks if len(t.detections) >= min_frames]
    dropped = len(tracks) - len(result)
    if dropped > 0:
        logger.debug(f"filter_by_min_frames: dropped {dropped} tracks (min={min_frames})")
    return result


def filter_by_confidence(tracks: list[Track], min_confidence: float = 0.4) -> list[Track]:
    """Remove detections below confidence threshold. Drop tracks with no remaining detections."""
    result = []
    for track in tracks:
        filtered_dets = [d for d in track.detections if d.confidence >= min_confidence]
        if filtered_dets:
            result.append(Track(
                track_id=track.track_id,
                class_name=track.class_name,
                detections=filtered_dets,
            ))
    dropped = len(tracks) - len(result)
    if dropped > 0:
        logger.debug(f"filter_by_confidence: dropped {dropped} tracks (min_conf={min_confidence})")
    return result


def filter_tracks_by_roi(
    tracks: list[Track],
    polygon: Polygon,
    mode: str = "inside",
) -> list[Track]:
    """
    Spatial filter: keep/remove detections based on their bbox center vs. a polygon.

    Args:
        tracks: Input tracks.
        polygon: Shapely Polygon in video pixel coordinates.
        mode: Filtering mode. Phase 1 supports "inside" only.
            - "inside": Keep detections whose bbox center is inside the polygon.
            - "outside": Keep detections whose bbox center is outside the polygon.

    Returns:
        Tracks with only the detections that pass the spatial filter.
        Tracks with no remaining detections are dropped.
    """
    if mode not in ("inside", "outside"):
        logger.warning(f"ROI filter mode '{mode}' not yet implemented, falling back to 'inside'")
        mode = "inside"

    result = []
    total_dets_before = sum(len(t.detections) for t in tracks)
    total_dets_after = 0

    for track in tracks:
        filtered_dets = []
        for det in track.detections:
            center_x, center_y = det.bbox.center
            point = Point(center_x, center_y)
            is_inside = polygon.contains(point)

            if mode == "inside" and is_inside:
                filtered_dets.append(det)
            elif mode == "outside" and not is_inside:
                filtered_dets.append(det)

        if filtered_dets:
            result.append(Track(
                track_id=track.track_id,
                class_name=track.class_name,
                detections=filtered_dets,
            ))
            total_dets_after += len(filtered_dets)

    logger.info(
        f"ROI filter (mode={mode}): {len(tracks)} tracks → {len(result)} tracks, "
        f"{total_dets_before} dets → {total_dets_after} dets"
    )

    return result


def apply_filters(
    tracks: list[Track],
    roi_polygon: list[dict] | None = None,
    roi_mode: str = "inside",
    min_track_frames: int = 5,
    min_confidence: float = 0.4,
) -> list[Track]:
    """
    Apply all filters in sequence. Convenience function used by the pipeline runner.

    Args:
        tracks: Raw tracks from vision layer.
        roi_polygon: List of {"x": float, "y": float} points, or None if no ROI.
        roi_mode: ROI filtering mode (default: "inside").
        min_track_frames: Minimum detections per track.
        min_confidence: Minimum detection confidence.

    Returns:
        Filtered tracks.
    """
    result = tracks

    # 1. Quality filters (always run)
    result = filter_by_min_frames(result, min_track_frames)
    result = filter_by_confidence(result, min_confidence)

    # 2. ROI spatial filter (if polygon provided)
    if roi_polygon is not None:
        polygon = Polygon([(p["x"], p["y"]) for p in roi_polygon])
        if polygon.is_valid:
            result = filter_tracks_by_roi(result, polygon, mode=roi_mode)
        else:
            logger.warning("ROI polygon is invalid, skipping ROI filter")

    # Future: appearance filter, object association filter

    return result
