"""
Task registry — maps task names to metric functions.

Each metric function has the signature:
    fn(tracks, params, roi_polygon, fps, video_duration) -> dict

Adding a new metric:
1. Write the function in backend/app/metrics/my_metric.py
2. Import and register it here
3. The pipeline runner will pick it up automatically

Spec: PIPELINE-LOGIC.md Section 7.2.
"""

from typing import Callable

from app.metrics.dwell import compute_dwell_count

# Maps task name → metric function
TASK_REGISTRY: dict[str, Callable] = {
    "dwell_count": compute_dwell_count,
}


def get_available_tasks() -> list[str]:
    """Return list of registered task names."""
    return list(TASK_REGISTRY.keys())
