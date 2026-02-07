"""
YOLO detection + tracking wrapper.

Runs Ultralytics YOLO .track() on a video file and returns a list of Track
objects (see models.py). Each Track groups all detections for one tracked object
across the video.

Uses YOLO's built-in ByteTrack tracker — no separate tracker library needed.
"""

import logging
from collections import defaultdict

from ultralytics import YOLO

from app.vision.models import BBox, Detection, Track

logger = logging.getLogger(__name__)

# YOLO COCO class names — maps class index to name
# The full list is available via model.names; we keep a reference for filtering
_COCO_PERSON_CLASS_ID = 0  # "person" is class 0 in COCO

# Module-level model cache so we don't reload on every call
_model_cache: dict[str, YOLO] = {}


def _get_model(model_name: str) -> YOLO:
    """Load (or retrieve from cache) a YOLO model by name."""
    if model_name not in _model_cache:
        logger.info(f"Loading YOLO model: {model_name}")
        _model_cache[model_name] = YOLO(model_name)
        logger.info(f"Model {model_name} loaded successfully")
    return _model_cache[model_name]


def _class_name_to_ids(model: YOLO, class_names: list[str]) -> list[int]:
    """Map human-readable class names to YOLO class IDs."""
    name_to_id = {name: idx for idx, name in model.names.items()}
    ids = []
    for name in class_names:
        if name in name_to_id:
            ids.append(name_to_id[name])
        else:
            logger.warning(f"Class '{name}' not found in model. Available: {list(name_to_id.keys())[:10]}...")
    return ids


def run_detection_and_tracking(
    video_path: str,
    model_name: str = "yolo11n.pt",
    detect_classes: list[str] | None = None,
    confidence: float = 0.4,
    sample_fps: float | None = None,
) -> list[Track]:
    """
    Run YOLO detection + tracking on a video file.

    Args:
        video_path: Path to the video file.
        model_name: YOLO model file (e.g. "yolo11n.pt"). Auto-downloaded on first use.
        detect_classes: List of class names to detect (e.g. ["person"]). None = all classes.
        confidence: Minimum detection confidence threshold.
        sample_fps: If set, process only N frames per second. None = every frame.

    Returns:
        List of Track objects, each containing all detections for one tracked entity.
    """
    model = _get_model(model_name)

    # Determine which classes to filter for
    class_ids = None
    if detect_classes:
        class_ids = _class_name_to_ids(model, detect_classes)
        if not class_ids:
            logger.warning(f"No valid class IDs found for {detect_classes}, detecting all classes")
            class_ids = None

    # Get video fps for timestamp calculation
    import cv2
    cap = cv2.VideoCapture(video_path)
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    if video_fps <= 0:
        video_fps = 30.0  # fallback
        logger.warning(f"Could not read video FPS, defaulting to {video_fps}")

    # Run YOLO .track() — streams through the video frame by frame
    # persist=True keeps track IDs consistent across frames
    logger.info(f"Running YOLO tracking on {video_path} (model={model_name}, conf={confidence})")

    track_kwargs = {
        "source": video_path,
        "conf": confidence,
        "persist": True,
        "stream": True,       # Process frame-by-frame (memory efficient)
        "verbose": False,     # Suppress per-frame output
    }
    if class_ids is not None:
        track_kwargs["classes"] = class_ids

    # Collect detections grouped by track_id
    tracks_dict: dict[int, list[Detection]] = defaultdict(list)
    frame_index = 0
    frames_processed = 0

    for result in model.track(**track_kwargs):
        # Handle sample_fps: skip frames if needed
        if sample_fps is not None and sample_fps > 0:
            target_interval = video_fps / sample_fps
            if frame_index % max(1, int(target_interval)) != 0:
                frame_index += 1
                continue

        timestamp_sec = frame_index / video_fps

        # result.boxes contains all detections for this frame
        boxes = result.boxes
        if boxes is not None and len(boxes) > 0:
            for i in range(len(boxes)):
                # Get bounding box coordinates (xyxy format)
                xyxy = boxes.xyxy[i].cpu().numpy()
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = model.names[cls_id]

                # Get track ID (may be None if tracking failed for this detection)
                track_id = None
                if boxes.id is not None:
                    track_id = int(boxes.id[i].cpu().numpy())

                if track_id is None:
                    # Skip untracked detections — we need track IDs for metrics
                    continue

                detection = Detection(
                    frame_index=frame_index,
                    timestamp_sec=round(timestamp_sec, 4),
                    bbox=BBox(
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                    ),
                    class_name=cls_name,
                    confidence=round(conf, 4),
                    track_id=track_id,
                )

                tracks_dict[track_id].append(detection)

        frame_index += 1
        frames_processed += 1

    # Build Track objects from grouped detections
    tracks: list[Track] = []
    for track_id, detections in sorted(tracks_dict.items()):
        # Sort detections by frame index (should already be sorted, but be safe)
        detections.sort(key=lambda d: d.frame_index)
        class_name = detections[0].class_name  # Use first detection's class
        tracks.append(Track(
            track_id=track_id,
            class_name=class_name,
            detections=detections,
        ))

    logger.info(
        f"Tracking complete: {frames_processed} frames processed, "
        f"{len(tracks)} tracks found"
    )

    return tracks
