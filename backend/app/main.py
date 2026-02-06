"""
Minimal FastAPI backend for video upload and metadata extraction
Receives video files from frontend, saves them, and extracts metadata using OpenCV
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uuid
import shutil
from pathlib import Path
from app.core.decode import extract_metadata

# Create FastAPI app instance
app = FastAPI(title="Video Analytics Backend")

# Configure CORS to allow frontend (Next.js) to call this backend
# Without this, browser will block requests from localhost:3000 to localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Define upload directory path
UPLOAD_DIR = Path("uploads")

# Create uploads folder if it doesn't exist
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/")
async def root():
    """Health check endpoint - confirms backend is running"""
    return {"status": "ok", "message": "Video Analytics Backend is running"}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    Upload endpoint - receives video file from frontend
    
    Process:
    1. Generate unique ID for the video
    2. Save file to uploads/ folder
    3. Return video_id to frontend
    
    Args:
        file: Video file uploaded from frontend
        
    Returns:
        JSON with video_id and original filename
    """
    
    # Generate a unique identifier for this video (e.g., "a1b2c3d4-...")
    video_id = str(uuid.uuid4())
    
    # Create file path: uploads/a1b2c3d4-....mp4
    file_path = UPLOAD_DIR / f"{video_id}.mp4"
    
    # Save the uploaded file to disk
    # We open the file in write-binary mode and copy the uploaded content
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Return success response with video ID
    return {
        "video_id": video_id,
        "filename": file.filename,
        "message": "Video uploaded successfully"
    }


@app.get("/api/video/{video_id}/metadata")
async def get_video_metadata(video_id: str):
    """
    Get metadata for an uploaded video using OpenCV
    
    Process:
    1. Find the video file by ID
    2. Use OpenCV to extract metadata (fps, frame count, duration, etc.)
    3. Return metadata as JSON
    
    Args:
        video_id: Unique identifier for the video
        
    Returns:
        JSON with video metadata
    """
    
    # Construct path to the video file
    video_path = UPLOAD_DIR / f"{video_id}.mp4"
    
    # Check if video exists
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Extract metadata using OpenCV
    try:
        metadata = extract_metadata(str(video_path))
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(e)}")


@app.get("/api/video/{video_id}")
async def get_video(video_id: str):
    """
    Serve the video file so frontend can play it
    
    Process:
    1. Find the video file by ID
    2. Return it as a file response (browser can play it)
    
    Args:
        video_id: Unique identifier for the video
        
    Returns:
        Video file that can be played in browser
    """
    
    # Construct path to the video file
    video_path = UPLOAD_DIR / f"{video_id}.mp4"
    
    # Check if video exists
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Return video file with proper content type
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"{video_id}.mp4"
    )
