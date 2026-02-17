"""
Track filtering functions.

Each filter is a pure function: tracks in, tracks out.
Filters run in sequence: quality → ROI → appearance → (future: association).

Spec: PIPELINE-LOGIC.md Section 7.3 and Section 9.1.
"""

import logging
from typing import Optional

import cv2
import numpy as np
from shapely.geometry import Point, Polygon

from app.vision.models import Track, Detection
from app.vision.color import get_color_fraction, crop_to_region

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


def _detection_inside_roi(det: Detection, polygon: Polygon) -> bool:
    """Check if detection center is inside polygon."""
    center_x, center_y = det.bbox.center
    return polygon.contains(Point(center_x, center_y))


def _track_has_entry(track: Track, polygon: Polygon) -> bool:
    """
    Return True if track has at least one outside→inside transition.
    A track that starts inside (already in ROI when first seen) does NOT count as entered.
    Tracks must be sorted by frame_index.
    """
    sorted_dets = sorted(track.detections, key=lambda d: d.frame_index)
    if not sorted_dets:
        return False
    was_outside = not _detection_inside_roi(sorted_dets[0], polygon)
    for det in sorted_dets[1:]:
        is_inside = _detection_inside_roi(det, polygon)
        if was_outside and is_inside:
            return True
        was_outside = not is_inside
    return False


def _track_has_exit(track: Track, polygon: Polygon) -> bool:
    """
    Return True if track has at least one inside→outside transition.
    A track that ends inside (never left ROI) does NOT count as exited.
    """
    sorted_dets = sorted(track.detections, key=lambda d: d.frame_index)
    if not sorted_dets:
        return False
    was_inside = _detection_inside_roi(sorted_dets[0], polygon)
    for det in sorted_dets[1:]:
        is_inside = _detection_inside_roi(det, polygon)
        if was_inside and not is_inside:
            return True
        was_inside = is_inside
    return False


def _track_crosses_roi(track: Track, polygon: Polygon) -> bool:
    """
    Return True if track has detections both inside AND outside the polygon.
    """
    has_inside = False
    has_outside = False
    for det in track.detections:
        if _detection_inside_roi(det, polygon):
            has_inside = True
        else:
            has_outside = True
        if has_inside and has_outside:
            return True
    return False


def filter_tracks_by_roi(
    tracks: list[Track],
    polygon: Polygon,
    mode: str = "inside",
) -> list[Track]:
    """
    Spatial filter: keep/remove detections or tracks based on their bbox center vs. a polygon.

    Args:
        tracks: Input tracks.
        polygon: Shapely Polygon in video pixel coordinates.
        mode: Filtering mode:
            - "inside": Keep detections whose bbox center is inside the polygon.
            - "outside": Keep detections whose bbox center is outside the polygon.
            - "enters": Keep full tracks that have at least one outside→inside transition.
            - "exits": Keep full tracks that have at least one inside→outside transition.
            - "crosses": Keep full tracks that have detections both inside and outside.

    Returns:
        For "inside"/"outside": Tracks with only the detections that pass.
        For "enters"/"crosses": Full tracks that qualify (all detections kept).
    """
    if mode not in ("inside", "outside", "enters", "exits", "crosses"):
        logger.warning(f"ROI filter mode '{mode}' not recognized, falling back to 'inside'")
        mode = "inside"

    result = []
    total_dets_before = sum(len(t.detections) for t in tracks)
    total_dets_after = 0

    if mode in ("enters", "exits", "crosses"):
        # Keep full tracks that qualify for traffic-style metrics
        for track in tracks:
            if mode == "enters" and _track_has_entry(track, polygon):
                result.append(track)
                total_dets_after += len(track.detections)
            elif mode == "exits" and _track_has_exit(track, polygon):
                result.append(track)
                total_dets_after += len(track.detections)
            elif mode == "crosses" and _track_crosses_roi(track, polygon):
                result.append(track)
                total_dets_after += len(track.detections)
    else:
        # Per-detection filtering for "inside" and "outside"
        for track in tracks:
            filtered_dets = []
            for det in track.detections:
                is_inside = _detection_inside_roi(det, polygon)
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


def filter_by_appearance(
    tracks: list[Track],
    video_path: str,
    color: str,
    color_region: str = "torso",
    color_threshold: float = 0.12,
    n_samples: int = 8,
) -> list[Track]:
    """
    Keep only tracks where the object's bounding box shows the target color.

    Strategy:
        - Open the video once with OpenCV.
        - For each track, sample up to `n_samples` evenly-spaced detections.
        - Seek to the detection's frame, crop to `color_region` within the bbox.
        - Compute fraction of pixels matching `color` using HSV ranges.
        - Keep the track if the mean color fraction across samples >= `color_threshold`.

    Args:
        tracks: Filtered tracks (after quality + ROI filters).
        video_path: Path to the original video file (needed to read frames).
        color: Target color name, e.g. "green", "red", "blue".
        color_region: Bbox sub-region to sample — "torso"|"upper"|"lower"|"full".
        color_threshold: Minimum mean color fraction to keep a track (default 12 %).
        n_samples: How many frames to sample per track (default 8).

    Returns:
        Tracks whose appearance matches the target color.
    """
    if not tracks:
        return tracks

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"filter_by_appearance: cannot open video at {video_path}")
        return tracks  # fail-open: return all tracks rather than crashing

    result: list[Track] = []

    for track in tracks:
        if not track.detections:
            continue

        # Sample evenly-spaced detections (at most n_samples)
        dets = track.detections
        step = max(1, len(dets) // n_samples)
        sampled = dets[::step][:n_samples]

        fractions: list[float] = []

        for det in sampled:
            # Seek to the frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, det.frame_index)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            crop = crop_to_region(
                frame,
                det.bbox.x1, det.bbox.y1,
                det.bbox.x2, det.bbox.y2,
                color_region,
            )
            if crop.size == 0:
                continue

            frac = get_color_fraction(crop, color)
            fractions.append(frac)

        if not fractions:
            # Could not read any frame — keep track to avoid false negatives
            result.append(track)
            continue

        mean_frac = np.mean(fractions)
        if mean_frac >= color_threshold:
            result.append(track)

    cap.release()

    kept = len(result)
    dropped = len(tracks) - kept
    logger.info(
        f"filter_by_appearance (color='{color}', region='{color_region}', "
        f"threshold={color_threshold:.0%}): "
        f"{len(tracks)} tracks → {kept} kept, {dropped} dropped"
    )
    return result


def apply_filters(
    tracks: list[Track],
    roi_polygon: list[dict] | None = None,
    roi_mode: str = "inside",
    min_track_frames: int = 5,
    min_confidence: float = 0.4,
    appearance: Optional[dict] = None,
    video_path: Optional[str] = None,
) -> list[Track]:
    """
    Apply all filters in sequence. Convenience function used by the pipeline runner.

    Args:
        tracks: Raw tracks from vision layer.
        roi_polygon: List of {"x": float, "y": float} points, or None if no ROI.
        roi_mode: ROI filtering mode (default: "inside").
        min_track_frames: Minimum detections per track.
        min_confidence: Minimum detection confidence.
        appearance: Optional AppearanceFilter dict with "color" and "color_region" keys.
        video_path: Path to video file — required when appearance filter is set.

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

    # 3. Appearance (color) filter
    if appearance and appearance.get("color"):
        if video_path:
            result = filter_by_appearance(
                tracks=result,
                video_path=video_path,
                color=appearance["color"],
                color_region=appearance.get("color_region", "torso"),
            )
        else:
            logger.warning(
                "Appearance filter requested but video_path not provided — skipping"
            )

    return result
