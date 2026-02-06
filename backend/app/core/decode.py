"""
Video decoding and metadata extraction using OpenCV
Simple functions to read video properties
"""

import cv2
from pathlib import Path


def extract_metadata(video_path: str) -> dict:
    """
    Extract basic metadata from a video file using OpenCV
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Dictionary with video metadata (fps, frame_count, width, height, duration)
    """
    
    # Open the video file
    cap = cv2.VideoCapture(video_path)
    
    # Check if video opened successfully
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    
    # Read video properties using OpenCV property constants
    fps = cap.get(cv2.CAP_PROP_FPS)                          # Frames per second
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))     # Total number of frames
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))           # Video width in pixels
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))         # Video height in pixels
    
    # Calculate duration in seconds
    duration = frame_count / fps if fps > 0 else 0
    
    # Close the video file
    cap.release()
    
    # Return metadata as a dictionary
    return {
        "fps": round(fps, 2),
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration": round(duration, 2)
    }
