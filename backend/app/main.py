"""
Minimal FastAPI backend for video upload
Receives video files from frontend and saves them to disk
"""

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uuid
import shutil
from pathlib import Path

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
