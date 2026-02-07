"""
Pipeline runner — orchestrates the full analysis pipeline.

Pipeline steps:
  1. Decode:  Extract video metadata (fps, duration, etc.)
  2. Vision:  Run YOLO detection + tracking → list[Track]
  3. Filter:  Apply ROI filter + quality filters → filtered tracks
  4. Metric:  Run the selected task function → events + aggregates
  5. Visualize: Run task-specific visualizer → annotated video (when registered)
  6. Format:  Attach metadata and return

Spec: PIPELINE-LOGIC.md Section 7.1.
"""

import logging
import time
from pathlib import Path

from app.core.decode import extract_metadata
from app.vision.detector import run_detection_and_tracking
from app.pipeline.filters import apply_filters
from app.pipeline.registry import TASK_REGISTRY
from app.visualizers.registry import get_visualizer

logger = logging.getLogger(__name__)

# Annotated videos written here (backend/annotated_cache/)
ANNOTATED_CACHE = Path(__file__).resolve().parent.parent.parent / "annotated_cache"


async def run_pipeline(
    video_path: str,
    plan: dict,
    roi_polygon: list[dict] | None,
) -> dict:
    """
    Execute the full analysis pipeline from plan dict to results.

    Args:
        video_path: Path to the video file.
        plan: Analysis plan dict with keys:
            - task (str): Metric function name from TASK_REGISTRY.
            - object (str): Primary object to detect (e.g. "person").
            - use_roi (bool): Whether to use ROI as spatial filter.
            - params (dict): Task-specific parameters.
            - vision (dict, optional): Vision config overrides.
            - filters (dict, optional): Filter config overrides.
        roi_polygon: List of {"x": float, "y": float} points, or None.

    Returns:
        Dict with "events", "aggregates", and "metadata" keys.
    """
    start_time = time.time()
    task_name = plan.get("task", "dwell_count")
    use_roi = plan.get("use_roi", True)
    params = plan.get("params", {})

    # Vision config (with defaults)
    vision_config = plan.get("vision", {})
    model_name = vision_config.get("model", "yolo11n.pt")
    # Ensure .pt extension
    if not model_name.endswith(".pt"):
        model_name = f"{model_name}.pt"
    detect_classes = vision_config.get("detect_classes", [plan.get("object", "person")])
    confidence = vision_config.get("confidence_threshold", 0.4)
    sample_fps = vision_config.get("sample_fps", None)

    # Filter config (with defaults)
    filter_config = plan.get("filters", {})
    roi_mode = filter_config.get("roi_mode", "inside")
    min_track_frames = filter_config.get("min_track_frames", 5)
    min_confidence = filter_config.get("min_confidence", 0.4)

    # Validate task exists
    if task_name not in TASK_REGISTRY:
        raise ValueError(
            f"Unknown task '{task_name}'. Available tasks: {list(TASK_REGISTRY.keys())}"
        )

    # ── Step 1: Decode ──
    logger.info(f"Pipeline Step 1/4: Decoding video metadata from {video_path}")
    video_meta = extract_metadata(video_path)
    fps = video_meta["fps"]
    video_duration = video_meta["duration"]

    # ── Step 2: Vision (YOLO detect + track) ──
    logger.info(f"Pipeline Step 2/4: Running YOLO tracking (model={model_name})")
    tracks = run_detection_and_tracking(
        video_path=video_path,
        model_name=model_name,
        detect_classes=detect_classes,
        confidence=confidence,
        sample_fps=sample_fps,
    )
    tracks_found = len(tracks)

    # ── Step 3: Filter ──
    logger.info(f"Pipeline Step 3/4: Applying filters (roi={use_roi}, mode={roi_mode})")
    effective_roi = roi_polygon if use_roi else None
    filtered_tracks = apply_filters(
        tracks=tracks,
        roi_polygon=effective_roi,
        roi_mode=roi_mode,
        min_track_frames=min_track_frames,
        min_confidence=min_confidence,
    )
    tracks_after_filter = len(filtered_tracks)

    # ── Step 4: Metric ──
    logger.info(f"Pipeline Step 4/4: Computing metric '{task_name}'")
    task_fn = TASK_REGISTRY[task_name]
    result = task_fn(
        tracks=filtered_tracks,
        params=params,
        roi_polygon=roi_polygon if use_roi else None,
        fps=fps,
        video_duration=video_duration,
    )

    # ── Step 5: Visualize (same run as metric) ──
    video_id = Path(video_path).stem
    vis_fn = get_visualizer(task_name)
    if vis_fn:
        try:
            out_path = vis_fn(
                all_tracks=tracks,
                filtered_tracks=filtered_tracks,
                roi_polygon=roi_polygon if use_roi else None,
                params=params,
                events=result.get("events", []),
                video_path=video_path,
                video_id=video_id,
                fps=fps,
                width=video_meta["width"],
                height=video_meta["height"],
                frame_count=video_meta["frame_count"],
                output_dir=ANNOTATED_CACHE,
            )
            if out_path and out_path.exists():
                result["annotated_video_url"] = f"/api/video/{video_id}/annotated"
        except Exception as e:
            logger.warning(f"Visualizer failed for {task_name}: {e}")

    # ── Attach metadata ──
    processing_time = round(time.time() - start_time, 2)
    result["metadata"] = {
        "frames_processed": video_meta["frame_count"],
        "tracks_found": tracks_found,
        "tracks_after_filter": tracks_after_filter,
        "processing_time_sec": processing_time,
        "model_used": model_name,
        "video_fps": fps,
        "video_duration_sec": video_duration,
        "task": task_name,
    }

    logger.info(
        f"Pipeline complete in {processing_time}s: "
        f"{tracks_found} tracks → {tracks_after_filter} filtered → "
        f"{len(result.get('events', []))} events"
    )

    return result
