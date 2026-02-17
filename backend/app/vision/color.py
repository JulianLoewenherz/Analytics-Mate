"""
HSV-based color extraction from image crops.

Used by the appearance filter (filters.py) to match clothing/object color
against a user-specified color name (e.g. "green", "red", "blue").

How it works:
  1. Convert a BGR NumPy crop to HSV color space.
  2. For each registered color, compute the fraction of pixels that fall
     within its HSV range.
  3. Return either the dominant color name OR the fraction for a specific color.

Design notes:
  - OpenCV HSV scale: H ∈ [0, 179], S ∈ [0, 255], V ∈ [0, 255]
  - Colors with wrapping hue (red) use two masks merged with bitwise_or.
  - A pixel must meet both the saturation and value thresholds to count;
    this rejects very dark (shadow) and very washed-out pixels.
"""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── HSV color range definitions ───────────────────────────────────────────────
# Each entry is a list of (lower_bound, upper_bound) tuples.
# Multiple ranges support hue wrap-around (red) or broad definitions.
#
# Tuples are (H_lo, S_lo, V_lo), (H_hi, S_hi, V_hi) in OpenCV scale.

_COLOR_RANGES: dict[str, list[tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "red": [
        ((0, 70, 50), (10, 255, 255)),
        ((165, 70, 50), (179, 255, 255)),   # hue wraps around 0
    ],
    "orange": [
        ((11, 70, 50), (25, 255, 255)),
    ],
    "yellow": [
        ((26, 70, 50), (34, 255, 255)),
    ],
    "green": [
        ((35, 50, 50), (85, 255, 255)),
    ],
    "teal": [
        ((75, 50, 50), (95, 255, 255)),
    ],
    "blue": [
        ((95, 60, 50), (130, 255, 255)),
    ],
    "purple": [
        ((125, 50, 50), (155, 255, 255)),
    ],
    "pink": [
        ((145, 40, 100), (169, 255, 255)),
    ],
    "white": [
        ((0, 0, 180), (179, 40, 255)),      # very low saturation, high brightness
    ],
    "black": [
        ((0, 0, 0), (179, 255, 50)),        # very low brightness
    ],
    "gray": [
        ((0, 0, 50), (179, 40, 180)),       # low saturation, mid brightness
    ],
}

# Synonyms — map alternate names to canonical color keys
_SYNONYMS: dict[str, str] = {
    "grey": "gray",
    "violet": "purple",
    "magenta": "pink",
    "cyan": "teal",
    "lime": "green",
    "navy": "blue",
    "dark blue": "blue",
    "light blue": "blue",
    "olive": "green",
}


def _normalise_color_name(color: str) -> str:
    """Lowercase, strip, then resolve synonyms to canonical name."""
    key = color.strip().lower()
    return _SYNONYMS.get(key, key)


def get_color_fraction(crop: np.ndarray, color_name: str) -> float:
    """
    Return the fraction of pixels in a BGR crop that match the named color.

    Args:
        crop: BGR NumPy array (H x W x 3). Can be any non-zero size.
        color_name: A color name like "green", "red", "blue", "white", etc.

    Returns:
        Fraction in [0.0, 1.0]. Returns 0.0 if crop is empty or color unknown.
    """
    if crop is None or crop.size == 0:
        return 0.0

    canonical = _normalise_color_name(color_name)
    ranges = _COLOR_RANGES.get(canonical)
    if ranges is None:
        logger.warning(f"color.py: unknown color '{color_name}' (canonical='{canonical}'). "
                       f"Known colors: {list(_COLOR_RANGES.keys())}")
        return 0.0

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    total_pixels = hsv.shape[0] * hsv.shape[1]
    if total_pixels == 0:
        return 0.0

    # Merge masks for all sub-ranges (handles red's hue wrap)
    combined_mask = np.zeros((hsv.shape[0], hsv.shape[1]), dtype=np.uint8)
    for lo, hi in ranges:
        lo_arr = np.array(lo, dtype=np.uint8)
        hi_arr = np.array(hi, dtype=np.uint8)
        combined_mask = cv2.bitwise_or(combined_mask, cv2.inRange(hsv, lo_arr, hi_arr))

    matched = int(np.count_nonzero(combined_mask))
    return matched / total_pixels


def get_dominant_color(crop: np.ndarray) -> Optional[str]:
    """
    Return the dominant color name in a BGR crop.

    Iterates all registered color definitions and returns the name of the
    color with the highest pixel fraction. Returns None for empty crops.
    """
    if crop is None or crop.size == 0:
        return None

    best_color: Optional[str] = None
    best_fraction = 0.0

    for color_name in _COLOR_RANGES:
        frac = get_color_fraction(crop, color_name)
        if frac > best_fraction:
            best_fraction = frac
            best_color = color_name

    return best_color


def crop_to_region(frame: np.ndarray, bbox_x1: float, bbox_y1: float,
                   bbox_x2: float, bbox_y2: float, region: str) -> np.ndarray:
    """
    Crop a video frame to the specified sub-region of a bounding box.

    Args:
        frame: Full BGR video frame (H x W x 3).
        bbox_x1, bbox_y1, bbox_x2, bbox_y2: Bounding box in pixel coordinates.
        region: One of "torso" | "upper" | "lower" | "full".
            - "torso":  rows 20–60 % of bbox height, cols 20–80 % of bbox width.
                        Best for detecting shirt color; avoids head and background.
            - "upper":  top 50 % of bbox height (head + torso).
            - "lower":  bottom 50 % of bbox height (waist + legs).
            - "full":   entire bounding box.

    Returns:
        BGR sub-crop as NumPy array, or an empty array if coordinates are invalid.
    """
    h_frame, w_frame = frame.shape[:2]

    x1 = max(0, int(bbox_x1))
    y1 = max(0, int(bbox_y1))
    x2 = min(w_frame, int(bbox_x2))
    y2 = min(h_frame, int(bbox_y2))

    bw = x2 - x1
    bh = y2 - y1

    if bw <= 0 or bh <= 0:
        return np.zeros((0, 0, 3), dtype=np.uint8)

    if region == "torso":
        ry1 = y1 + int(0.20 * bh)
        ry2 = y1 + int(0.60 * bh)
        rx1 = x1 + int(0.20 * bw)
        rx2 = x1 + int(0.80 * bw)
    elif region == "upper":
        ry1 = y1
        ry2 = y1 + int(0.50 * bh)
        rx1 = x1
        rx2 = x2
    elif region == "lower":
        ry1 = y1 + int(0.50 * bh)
        ry2 = y2
        rx1 = x1
        rx2 = x2
    else:  # "full"
        ry1, ry2, rx1, rx2 = y1, y2, x1, x2

    ry1 = max(0, ry1)
    ry2 = min(h_frame, ry2)
    rx1 = max(0, rx1)
    rx2 = min(w_frame, rx2)

    if ry2 <= ry1 or rx2 <= rx1:
        return np.zeros((0, 0, 3), dtype=np.uint8)

    return frame[ry1:ry2, rx1:rx2].copy()
