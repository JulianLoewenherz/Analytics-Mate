"""
FastAPI backend for video upload, metadata extraction, and video analysis pipeline.
Receives video files from frontend, saves them, extracts metadata using OpenCV,
and runs YOLO-based analysis pipelines (detection, tracking, dwell metrics, etc.).
"""

import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
from app.core.decode import extract_metadata
from app.pipeline.runner import run_pipeline
from app.pipeline.registry import get_available_tasks
from app.pipeline.schema import AnalysisPlan
from app.planner.llm import generate_plan

from dotenv import load_dotenv
load_dotenv()  # Load .env before other imports that read env vars

# Configure logging for pipeline visibility
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


class ROISaveBody(BaseModel):
    """Request body for POST /api/video/{video_id}/roi. Polygon in video pixel coordinates."""
    polygon: list[dict]  # [{"x": number, "y": number}, ...]
    name: str | None = None


class AnalyzeRequest(BaseModel):
    """Request body for POST /api/video/{video_id}/analyze.

    Provide either:
    - prompt: Natural language question (e.g. "How many people loiter for 10 seconds?")
    - plan: Structured analysis plan dict (e.g. { "task": "dwell_count", ... })
    """
    prompt: Optional[str] = None  # Natural language -> LLM produces plan
    plan: Optional[dict] = None   # Direct plan (Phase 1 style)

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

# ROI storage: JSON file under app/storage/
STORAGE_DIR = Path(__file__).parent / "storage"
ROI_STORAGE_PATH = STORAGE_DIR / "roi_storage.json"
STORAGE_DIR.mkdir(exist_ok=True)
if not ROI_STORAGE_PATH.exists():
    ROI_STORAGE_PATH.write_text("{}")


@app.get("/")
async def root():
    """Health check endpoint - confirms backend is running"""
    return {"status": "ok", "message": "Video Analytics Backend is running"}


@app.get("/api/videos")
async def list_videos():
    """
    List all uploaded videos by scanning the uploads folder for *.mp4 files.
    Returns video_id (filename without .mp4) for each file.
    """
    videos = []
    if UPLOAD_DIR.exists():
        for path in UPLOAD_DIR.glob("*.mp4"):
            video_id = path.stem
            videos.append({"video_id": video_id})
    return {"videos": videos}


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


def _load_roi_storage() -> dict:
    """Load roi_storage.json. Returns dict keyed by video_id."""
    if not ROI_STORAGE_PATH.exists():
        return {}
    text = ROI_STORAGE_PATH.read_text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _save_roi_storage(data: dict) -> None:
    """Write roi_storage.json."""
    ROI_STORAGE_PATH.write_text(json.dumps(data, indent=2))


@app.post("/api/video/{video_id}/roi")
async def save_roi(video_id: str, body: ROISaveBody):
    """
    Save ROI polygon for a video.

    Expects JSON: {"polygon": [{"x": 100, "y": 200}, ...], "name": "optional"}.
    Validates at least 3 points with numeric x, y.
    """
    polygon = body.polygon
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise HTTPException(
            status_code=400,
            detail="polygon must have at least 3 points"
        )
    for i, pt in enumerate(polygon):
        if not isinstance(pt, dict) or "x" not in pt or "y" not in pt:
            raise HTTPException(
                status_code=400,
                detail=f"point {i} must be {{x: number, y: number}}"
            )
        try:
            float(pt["x"])
            float(pt["y"])
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"point {i} must have numeric x and y"
            )

    storage = _load_roi_storage()
    storage[video_id] = {
        "polygon": polygon,
        "name": body.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_roi_storage(storage)
    return {"status": "ok", "video_id": video_id}


@app.get("/api/video/{video_id}/roi")
async def get_roi(video_id: str):
    """
    Retrieve saved ROI for a video. Returns 404 if no ROI stored.
    """
    storage = _load_roi_storage()
    if video_id not in storage:
        raise HTTPException(status_code=404, detail="ROI not found")
    return storage[video_id]


# ─────────────────────────────────────────────────────────────
# Phase 1: Analysis Pipeline Endpoint
# ─────────────────────────────────────────────────────────────

@app.post("/api/video/{video_id}/analyze")
async def analyze_video(video_id: str, body: AnalyzeRequest):
    """
    Run the analysis pipeline on a video.

    Accepts either:
    - prompt: Natural language question → LLM produces plan → pipeline runs
    - plan: Structured plan dict → pipeline runs directly

    If the plan requires an ROI (use_roi: true) but no ROI is saved for this video,
    returns status "needs_roi" instead of running the pipeline.

    Request body (prompt):
        { "prompt": "How many people loiter for more than 10 seconds?" }

    Request body (plan):
        { "plan": { "task": "dwell_count", "object": "person", "use_roi": true, "params": { "dwell_threshold_seconds": 10 } } }

    Responses:
        200 with status "ok": Pipeline ran successfully, includes results.
        200 with status "needs_roi": Plan requires ROI but none exists for this video.
        404: Video not found.
        400: Invalid plan, unknown task, or missing prompt/plan.
    """
    # Require either prompt or plan
    if not body.prompt and not body.plan:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'prompt' (natural language) or 'plan' (structured JSON).",
        )

    video_path = UPLOAD_DIR / f"{video_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    plan: AnalysisPlan

    if body.prompt and body.prompt.strip():
        # Path A: Prompt → LLM → Plan
        try:
            video_meta = extract_metadata(str(video_path))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to extract video metadata: {e}")

        storage = _load_roi_storage()
        roi_exists = video_id in storage and storage[video_id].get("polygon") is not None

        try:
            plan = await generate_plan(
                prompt=body.prompt.strip(),
                video_id=video_id,
                video_meta=video_meta,
                roi_exists=roi_exists,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    else:
        # Path B: Plan provided directly
        try:
            plan = AnalysisPlan.model_validate(body.plan)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid plan: {e}")

        if plan.task.value not in get_available_tasks():
            raise HTTPException(
                status_code=400,
                detail=f"Unknown task '{plan.task.value}'. Available tasks: {get_available_tasks()}",
            )

    # Check if ROI is needed but not available
    roi_polygon = None
    if plan.use_roi:
        storage = _load_roi_storage()
        if video_id in storage:
            roi_polygon = storage[video_id].get("polygon")
        else:
            roi_instruction = plan.roi_instruction or "Draw a region of interest around the area you want to analyze."
            return {
                "status": "needs_roi",
                "plan": plan.model_dump(mode="json"),
                "roi_instruction": roi_instruction,
                "message": "This analysis needs a region of interest. Draw one on the video, then run again.",
            }

    # Run the pipeline
    try:
        logger.info(f"Starting analysis for video {video_id}, task={plan.task.value}")
        result = await run_pipeline(
            video_path=str(video_path),
            plan=plan.to_plan_dict(),
            roi_polygon=roi_polygon,
        )

        return {
            "status": "ok",
            "plan": plan.model_dump(mode="json"),
            "result": result,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Pipeline error for video {video_id}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
