"""
Task-specific video visualizers.

Each visualizer produces an annotated MP4 (bounding boxes, ROI, color-coding)
for a given metric type. Used by the pipeline when analysis runs.
"""

from app.visualizers.registry import VISUALIZER_REGISTRY, get_visualizer

__all__ = ["VISUALIZER_REGISTRY", "get_visualizer"]
