"""
Visualizer registry — maps task names to visualizer functions.

Each visualizer produces an annotated MP4 file and returns its path.
"""

from pathlib import Path
from typing import Callable

from app.visualizers.dwell import visualize_dwell

# Task name → visualizer function
# Signature: (all_tracks, filtered_tracks, roi_polygon, params, events, video_path,
#             video_id, fps, width, height, frame_count, output_dir) -> Path | None
VISUALIZER_REGISTRY: dict[str, Callable] = {
    "dwell_count": visualize_dwell,
}


def get_visualizer(task_name: str) -> Callable | None:
    """Return the visualizer for a task, or None if none registered."""
    return VISUALIZER_REGISTRY.get(task_name)
