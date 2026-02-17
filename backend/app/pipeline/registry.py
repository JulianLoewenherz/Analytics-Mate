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
from app.metrics.traffic import compute_traffic_count

# Maps task name → metric function
TASK_REGISTRY: dict[str, Callable] = {
    "dwell_count": compute_dwell_count,
    "traffic_count": compute_traffic_count,
}


def get_available_tasks() -> list[str]:
    """Return list of registered task names."""
    return list(TASK_REGISTRY.keys())


def get_task_docs() -> str:
    """Return task descriptions for the LLM system prompt."""
    docs = []
    docstrings = {
        "dwell_count": "For each track, compute how long its center stays inside the ROI. Emit events for tracks that dwell >= threshold. Use for: loitering, queue wait time, display engagement.",
        "traffic_count": "Count unique tracks that enter or exit the ROI. Detects outside→inside (entry) and inside→outside (exit). Use for: crosswalk counting, store entries/exits, foot traffic. Requires filters.roi_mode: 'enters' (for entry count), 'exits' (for exit count), or 'crosses'. Use params.count_mode: 'unique_entries' or 'unique_exits' accordingly.",
    }
    for name in TASK_REGISTRY:
        desc = docstrings.get(name, name.replace("_", " "))
        docs.append(f"- {name}: {desc}")
    return "\n".join(docs)
