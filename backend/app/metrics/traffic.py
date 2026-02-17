"""
Traffic count metric.

Count unique tracks that enter/cross/pass through the ROI.
Detects outside→inside (entry) and inside→outside (exit) transitions.
Emit instant events (not duration-based like dwell).

Spec: PIPELINE-LOGIC.md Section 8.2.
"""

import logging
from shapely.geometry import Point, Polygon

from app.vision.models import Track
from app.pipeline.filters import _detection_inside_roi

logger = logging.getLogger(__name__)


def _get_entry_exit_events(
    track: Track,
    polygon: Polygon,
    fps: float,
) -> tuple[list[dict], list[dict]]:
    """
    Detect entry and exit transitions for a track.
    Returns (entry_events, exit_events).
    """
    sorted_dets = sorted(track.detections, key=lambda d: d.frame_index)
    if not sorted_dets:
        return [], []

    entries = []
    exits = []
    # First frame state: track that starts inside didn't "enter" (we didn't see the transition)
    was_inside = _detection_inside_roi(sorted_dets[0], polygon)

    for det in sorted_dets[1:]:
        is_inside = _detection_inside_roi(det, polygon)

        if not was_inside and is_inside:
            # Outside → inside: entry
            entries.append({
                "type": "entry",
                "track_id": track.track_id,
                "time_sec": round(det.timestamp_sec, 2),
                "frame": det.frame_index,
                "direction": "in",
            })
        elif was_inside and not is_inside:
            # Inside → outside: exit
            exits.append({
                "type": "exit",
                "track_id": track.track_id,
                "time_sec": round(det.timestamp_sec, 2),
                "frame": det.frame_index,
                "direction": "out",
            })

        was_inside = is_inside

    return entries, exits


def compute_traffic_count(
    tracks: list[Track],
    params: dict,
    roi_polygon: list[dict] | None,
    fps: float,
    video_duration: float,
) -> dict:
    """
    Count entries and exits through an ROI.

    For each track, detect outside→inside (entry) and inside→outside (exit) transitions.
    Emit instant events and compute aggregates.

    Args:
        tracks: Filtered tracks (from ROI filter with mode "enters" or "crosses").
        params: Task-specific parameters:
            - count_mode (str, default "unique_entries"):
                - "unique_entries": Count tracks that entered (how many entered).
                - "unique_exits": Count tracks that exited (how many exited).
                - "unique_crossings": Count tracks that both entered AND exited.
                - "first_entry_only": Same as unique_entries (intrusion detection).
        roi_polygon: List of {"x": float, "y": float} points defining the ROI.
        fps: Video frames per second.
        video_duration: Total video duration in seconds.

    Returns:
        Dict with "events" (entry + exit events) and "aggregates".
    """
    count_mode = params.get("count_mode", "unique_entries")

    polygon = None
    if roi_polygon:
        polygon = Polygon([(p["x"], p["y"]) for p in roi_polygon])
        if not polygon.is_valid:
            logger.warning("ROI polygon is invalid in traffic metric")
            polygon = None

    if polygon is None:
        logger.warning("traffic_count requires an ROI polygon")
        return {
            "events": [],
            "aggregates": {"total_count": 0},
        }

    all_entries = []
    all_exits = []
    tracks_with_entry = set()
    tracks_with_exit = set()
    tracks_with_both = set()

    for track in tracks:
        entries, exits = _get_entry_exit_events(track, polygon, fps)

        if entries:
            tracks_with_entry.add(track.track_id)
            all_entries.extend(entries)
        if exits:
            tracks_with_exit.add(track.track_id)
            all_exits.extend(exits)
        if entries and exits:
            tracks_with_both.add(track.track_id)

    # Return only the aggregate that is meaningful for the selected count_mode.
    # Showing zero-valued counters for irrelevant modes adds clutter.
    if count_mode == "unique_entries":
        aggregates = {"unique_entries": len(tracks_with_entry)}
    elif count_mode == "unique_exits":
        aggregates = {"unique_exits": len(tracks_with_exit)}
    elif count_mode == "unique_crossings":
        aggregates = {
            "unique_crossings": len(tracks_with_both),
            "entries": len(all_entries),
            "exits": len(all_exits),
        }
    elif count_mode == "first_entry_only":
        aggregates = {"unique_entries": len(tracks_with_entry)}
    else:
        aggregates = {"unique_entries": len(tracks_with_entry)}
        logger.warning(f"Unknown count_mode '{count_mode}', using unique_entries")

    # Combine events (entries first, then exits, sorted by time)
    events = all_entries + all_exits
    events.sort(key=lambda e: (e["time_sec"], 0 if e["type"] == "entry" else 1))

    primary_count = list(aggregates.values())[0]
    logger.info(
        f"traffic_count: mode={count_mode}, {primary_count} tracks, "
        f"{len(all_entries)} entries, {len(all_exits)} exits"
    )

    return {"events": events, "aggregates": aggregates}
