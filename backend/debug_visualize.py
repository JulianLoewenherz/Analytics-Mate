"""
Debug Visualization Script — See the pipeline in action.

Runs the full Phase 1 pipeline on a video and produces:
  1. An annotated video (.mp4) with YOLO boxes, track IDs, ROI polygon, and color-coding
  2. A detailed step-by-step debug log printed to the terminal

Usage (from the backend/ directory, with venv activated):
    python debug_visualize.py

It uses the first video + ROI found in storage. You can also pass a video_id:
    python debug_visualize.py 398c65aa-1b2a-4915-8f4e-67b905fb32b5
"""

import sys
import json
import time
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
from shapely.geometry import Point, Polygon

# ── Add the backend directory to the Python path so imports work ──
sys.path.insert(0, str(Path(__file__).parent))

from app.core.decode import extract_metadata
from app.vision.detector import run_detection_and_tracking
from app.vision.models import Track, Detection
from app.pipeline.filters import (
    filter_by_min_frames,
    filter_by_confidence,
    filter_tracks_by_roi,
)
from app.metrics.dwell import compute_dwell_count, _find_contiguous_runs


# ── Configuration ──
DWELL_THRESHOLD = 0.0  # seconds — set to 0 to see ALL dwell events
OUTPUT_DIR = Path("debug_output")
OUTPUT_DIR.mkdir(exist_ok=True)


def load_roi_for_video(video_id: str) -> list[dict] | None:
    """Load saved ROI polygon from storage."""
    storage_path = Path(__file__).parent / "app" / "storage" / "roi_storage.json"
    if not storage_path.exists():
        return None
    data = json.loads(storage_path.read_text())
    if video_id in data:
        return data[video_id].get("polygon")
    return None


def get_first_video() -> tuple[str, Path]:
    """Find the first uploaded video."""
    uploads = Path("uploads")
    for path in uploads.glob("*.mp4"):
        return path.stem, path
    raise FileNotFoundError("No videos found in uploads/")


def build_frame_lookup(tracks: list[Track]) -> dict[int, list[Detection]]:
    """Build a dict mapping frame_index → list of Detections in that frame."""
    lookup: dict[int, list[Detection]] = defaultdict(list)
    for track in tracks:
        for det in track.detections:
            lookup[det.frame_index].append(det)
    return lookup


def is_inside_roi(det: Detection, polygon: Polygon | None) -> bool:
    """Check if a detection's bbox center is inside the ROI polygon."""
    if polygon is None:
        return True
    cx, cy = det.bbox.center
    return polygon.contains(Point(cx, cy))


def draw_roi_polygon(frame: np.ndarray, roi_points: list[dict], color=(255, 255, 0), thickness=2):
    """Draw the ROI polygon on a frame."""
    pts = np.array([(int(p["x"]), int(p["y"])) for p in roi_points], dtype=np.int32)
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=thickness)
    # Semi-transparent fill
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color=(255, 255, 0))
    cv2.addWeighted(overlay, 0.1, frame, 0.9, 0, frame)


def draw_detection(frame: np.ndarray, det: Detection, inside_roi: bool):
    """Draw a bounding box + track ID on a frame."""
    x1, y1, x2, y2 = int(det.bbox.x1), int(det.bbox.y1), int(det.bbox.x2), int(det.bbox.y2)

    # Green if inside ROI, red if outside
    color = (0, 220, 0) if inside_roi else (0, 0, 220)

    # Draw box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Draw track ID label
    label = f"#{det.track_id}"
    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(frame, (x1, y1 - label_size[1] - 8), (x1 + label_size[0] + 4, y1), color, -1)
    cv2.putText(frame, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # Draw center dot
    cx, cy = int(det.bbox.center[0]), int(det.bbox.center[1])
    cv2.circle(frame, (cx, cy), 4, color, -1)


def draw_info_overlay(frame: np.ndarray, frame_idx: int, timestamp: float, fps: float,
                      n_detections: int, n_inside: int):
    """Draw frame info text in the top-left corner."""
    lines = [
        f"Frame: {frame_idx}  |  Time: {timestamp:.2f}s",
        f"Detections: {n_detections}  |  Inside ROI: {n_inside}",
    ]
    y = 40
    for line in lines:
        cv2.putText(frame, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(frame, line, (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        y += 35


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    # ── Determine which video to use ──
    if len(sys.argv) > 1:
        video_id = sys.argv[1]
        video_path = Path("uploads") / f"{video_id}.mp4"
        if not video_path.exists():
            print(f"ERROR: Video file not found: {video_path}")
            sys.exit(1)
    else:
        video_id, video_path = get_first_video()

    roi_polygon_raw = load_roi_for_video(video_id)
    roi_polygon_shapely = None
    if roi_polygon_raw:
        roi_polygon_shapely = Polygon([(p["x"], p["y"]) for p in roi_polygon_raw])

    print("=" * 70)
    print("  PHASE 1 DEBUG VISUALIZER")
    print("=" * 70)
    print(f"  Video:  {video_path}")
    print(f"  ROI:    {'Yes (' + str(len(roi_polygon_raw)) + ' points)' if roi_polygon_raw else 'None'}")
    print(f"  Dwell threshold: {DWELL_THRESHOLD}s")
    print("=" * 70)

    # ══════════════════════════════════════════════════════
    #  STEP 1: DECODE
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  STEP 1: DECODE — Reading video metadata")
    print("=" * 70)

    meta = extract_metadata(str(video_path))
    fps = meta["fps"]
    frame_count = meta["frame_count"]
    duration = meta["duration"]
    width = meta["width"]
    height = meta["height"]

    print(f"  FPS:          {fps}")
    print(f"  Frame count:  {frame_count}")
    print(f"  Duration:     {duration}s")
    print(f"  Resolution:   {width} x {height}")

    # ══════════════════════════════════════════════════════
    #  STEP 2: VISION — Run YOLO detection + tracking
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  STEP 2: VISION — Running YOLO detection + tracking")
    print("  (This is the slow part — processing every frame...)")
    print("=" * 70)

    t0 = time.time()
    all_tracks = run_detection_and_tracking(
        video_path=str(video_path),
        model_name="yolo11n.pt",
        detect_classes=["person"],
        confidence=0.4,
    )
    vision_time = time.time() - t0

    print(f"\n  Done in {vision_time:.1f}s")
    print(f"  Total tracks found: {len(all_tracks)}")
    print()
    for track in all_tracks:
        first_frame = track.detections[0].frame_index
        last_frame = track.detections[-1].frame_index
        print(
            f"    Track #{track.track_id:>3d}:  {track.class_name:>8s}  "
            f"{track.frame_count:>4d} detections  "
            f"frames {first_frame}-{last_frame}  "
            f"({track.start_time:.2f}s - {track.end_time:.2f}s)  "
            f"duration={track.duration:.2f}s"
        )

    # ══════════════════════════════════════════════════════
    #  STEP 3: FILTER — Quality + ROI filtering
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  STEP 3: FILTER — Narrowing down tracks")
    print("=" * 70)

    # 3a: Min frames filter
    after_min_frames = filter_by_min_frames(all_tracks, min_frames=5)
    dropped_min = len(all_tracks) - len(after_min_frames)
    print(f"\n  3a. Min frames filter (min=5):")
    print(f"      {len(all_tracks)} tracks → {len(after_min_frames)} tracks (dropped {dropped_min})")

    # 3b: Confidence filter
    after_confidence = filter_by_confidence(after_min_frames, min_confidence=0.4)
    dropped_conf = len(after_min_frames) - len(after_confidence)
    print(f"\n  3b. Confidence filter (min=0.4):")
    print(f"      {len(after_min_frames)} tracks → {len(after_confidence)} tracks (dropped {dropped_conf})")

    # 3c: ROI filter
    if roi_polygon_shapely:
        after_roi = filter_tracks_by_roi(after_confidence, roi_polygon_shapely, mode="inside")
        dropped_roi = len(after_confidence) - len(after_roi)
        print(f"\n  3c. ROI filter (mode=inside):")
        print(f"      {len(after_confidence)} tracks → {len(after_roi)} tracks (dropped {dropped_roi})")
        print()
        for track in after_roi:
            original = next((t for t in all_tracks if t.track_id == track.track_id), None)
            orig_count = original.frame_count if original else "?"
            print(
                f"      Track #{track.track_id:>3d}: {orig_count} → {track.frame_count} detections "
                f"(kept {track.frame_count} inside ROI)"
            )
    else:
        after_roi = after_confidence
        print(f"\n  3c. ROI filter: SKIPPED (no ROI polygon)")

    filtered_tracks = after_roi

    # ══════════════════════════════════════════════════════
    #  STEP 4: METRIC — Dwell count computation
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print(f"  STEP 4: METRIC — dwell_count (threshold={DWELL_THRESHOLD}s)")
    print("=" * 70)

    # Manually walk through the dwell logic so we can print each step
    polygon_for_dwell = None
    if roi_polygon_raw:
        polygon_for_dwell = Polygon([(p["x"], p["y"]) for p in roi_polygon_raw])

    all_events = []

    for track in filtered_tracks:
        # Find inside frames
        inside_frames = []
        for det in track.detections:
            cx, cy = det.bbox.center
            if polygon_for_dwell is None or polygon_for_dwell.contains(Point(cx, cy)):
                inside_frames.append(det.frame_index)

        if not inside_frames:
            print(f"\n  Track #{track.track_id}: 0 frames inside ROI — skipped")
            continue

        # Find contiguous runs
        runs = _find_contiguous_runs(inside_frames)

        print(f"\n  Track #{track.track_id}: {len(inside_frames)} frames inside ROI")
        print(f"    Frame indices (first 10): {inside_frames[:10]}{'...' if len(inside_frames) > 10 else ''}")
        print(f"    Contiguous runs: {len(runs)}")

        for i, (run_start, run_end) in enumerate(runs):
            num_frames = run_end - run_start + 1
            duration_sec = num_frames / fps if fps > 0 else 0
            start_time = run_start / fps if fps > 0 else 0
            end_time = run_end / fps if fps > 0 else 0
            passes = duration_sec >= DWELL_THRESHOLD

            symbol = "✓ DWELL EVENT" if passes else "✗ below threshold"
            print(
                f"      Run {i + 1}: frames {run_start}-{run_end} ({num_frames} frames) "
                f"= {duration_sec:.2f}s  [{start_time:.2f}s → {end_time:.2f}s]  {symbol}"
            )

            if passes:
                all_events.append({
                    "track_id": track.track_id,
                    "start_time_sec": round(start_time, 2),
                    "end_time_sec": round(end_time, 2),
                    "duration_sec": round(duration_sec, 2),
                    "frame_start": run_start,
                    "frame_end": run_end,
                })

    # ══════════════════════════════════════════════════════
    #  RESULT SUMMARY
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  RESULT SUMMARY")
    print("=" * 70)
    print(f"  Total dwell events: {len(all_events)}")
    if all_events:
        unique_ids = set(e["track_id"] for e in all_events)
        durations = [e["duration_sec"] for e in all_events]
        print(f"  Unique dwellers:    {len(unique_ids)}")
        print(f"  Average duration:   {sum(durations) / len(durations):.2f}s")
        print(f"  Max duration:       {max(durations):.2f}s")
        print(f"  Min duration:       {min(durations):.2f}s")
        print()
        for e in all_events:
            print(
                f"    Event: Track #{e['track_id']}  "
                f"{e['start_time_sec']:.2f}s → {e['end_time_sec']:.2f}s  "
                f"({e['duration_sec']:.2f}s)  "
                f"frames {e['frame_start']}-{e['frame_end']}"
            )
    else:
        print("  No dwell events found.")

    # ══════════════════════════════════════════════════════
    #  RENDER ANNOTATED VIDEO
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  RENDERING ANNOTATED VIDEO")
    print("  (Drawing boxes, ROI, and color-coding on every frame...)")
    print("=" * 70)

    # Build frame lookup from ALL tracks (not just filtered) so we can see
    # everything YOLO detected — filtered-out tracks will be drawn in red
    frame_lookup_all = build_frame_lookup(all_tracks)

    # Set of track IDs that survived filtering (these are "inside ROI")
    surviving_track_ids = set(t.track_id for t in filtered_tracks)

    # For surviving tracks, build a set of (track_id, frame_index) pairs
    # that are actually inside the ROI (for precise per-frame coloring)
    inside_roi_pairs: set[tuple[int, int]] = set()
    if roi_polygon_shapely:
        for track in filtered_tracks:
            for det in track.detections:
                cx, cy = det.bbox.center
                if roi_polygon_shapely.contains(Point(cx, cy)):
                    inside_roi_pairs.add((det.track_id, det.frame_index))
    else:
        # No ROI — everything is "inside"
        for track in all_tracks:
            for det in track.detections:
                inside_roi_pairs.add((det.track_id, det.frame_index))

    # Open video for reading
    cap = cv2.VideoCapture(str(video_path))
    output_path = OUTPUT_DIR / f"annotated_{video_id}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    frame_idx = 0
    render_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / fps if fps > 0 else 0

        # Draw ROI polygon
        if roi_polygon_raw:
            draw_roi_polygon(frame, roi_polygon_raw)

        # Draw all detections for this frame
        dets_in_frame = frame_lookup_all.get(frame_idx, [])
        n_inside = 0

        for det in dets_in_frame:
            det_inside = (det.track_id, det.frame_index) in inside_roi_pairs
            if det_inside:
                n_inside += 1
            draw_detection(frame, det, inside_roi=det_inside)

        # Draw info overlay
        draw_info_overlay(frame, frame_idx, timestamp, fps, len(dets_in_frame), n_inside)

        out.write(frame)
        frame_idx += 1

        # Progress indicator
        if frame_idx % 200 == 0:
            pct = (frame_idx / frame_count) * 100
            print(f"  Rendered {frame_idx}/{frame_count} frames ({pct:.0f}%)")

    cap.release()
    out.release()
    render_time = time.time() - render_start

    print(f"\n  Done in {render_time:.1f}s")
    print(f"  Output saved to: {output_path}")
    print(f"\n  Open it with:  open \"{output_path}\"")

    print("\n" + "=" * 70)
    print("  ALL DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
