# Phase 1: Foundation — One Metric End-to-End (No LLM Yet)

**Goal:** Run a single metric (`dwell_count`) on a real video with a drawn ROI, using a **hardcoded** plan. No natural language, no planner.

**Prerequisites (already done):**
- Video upload + playback working (`POST /api/upload`, `GET /api/video/{id}`)
- Video metadata extraction via OpenCV (`GET /api/video/{id}/metadata`)
- ROI drawing + persistence (`POST /api/video/{id}/roi`, `GET /api/video/{id}/roi`)

---

## Step 1a: Dependencies

**What:** Add `ultralytics` (YOLO detection + tracking) and `shapely` (polygon geometry) to `backend/requirements.txt`.

**Model selection:** Use YOLO11n (`yolo11n.pt`) as the default since it's the most broadly available in current `ultralytics` releases. The code will attempt `yolo11n.pt`; the model file is auto-downloaded on first use.

**Files changed:**
- `backend/requirements.txt`

**Verification:**
```bash
cd backend && source venv/bin/activate
pip install -r requirements.txt
python -c "from ultralytics import YOLO; m = YOLO('yolo11n.pt'); print('OK')"
python -c "from shapely.geometry import Point, Polygon; print('OK')"
```

---

## Step 1b: Vision — `detector.py` + `models.py`

**What:** Create the vision layer that wraps YOLO's `.track()` method. Produces `list[Track]` — the core data structure consumed by everything downstream (filters, metrics).

**Data structures (`backend/app/vision/models.py`):**

```
BBox          — bounding box with x1, y1, x2, y2 + center/width/height properties
Detection     — one detection in one frame: bbox, class, confidence, track_id, timestamp
Track         — a tracked object across frames: track_id, class_name, list[Detection]
```

These Pydantic models match the spec from PIPELINE-LOGIC.md Section 6.5.

**Detector (`backend/app/vision/detector.py`):**

```python
def run_detection_and_tracking(
    video_path: str,
    model_name: str = "yolo11n.pt",
    detect_classes: list[str] | None = None,
    confidence: float = 0.4,
    sample_fps: float | None = None,
) -> list[Track]:
```

- Loads YOLO model (cached after first load)
- Runs `model.track(source=video_path, ...)` frame by frame
- Groups detections into Track objects by track_id
- Filters by `detect_classes` if specified
- Returns `list[Track]` sorted by track_id

**Files created:**
- `backend/app/vision/__init__.py`
- `backend/app/vision/models.py`
- `backend/app/vision/detector.py`

**Verification:**
```python
from app.vision.detector import run_detection_and_tracking
tracks = run_detection_and_tracking("uploads/some-video.mp4")
print(f"Found {len(tracks)} tracks")
for t in tracks[:3]:
    print(f"  Track {t.track_id}: {len(t.detections)} detections, {t.class_name}")
```

---

## Step 1c: ROI Filter — `filters.py`

**What:** Spatial filter using Shapely. Given tracks and a polygon, filter detections to only those whose bbox center is inside the polygon.

**Function:**

```python
def filter_tracks_by_roi(
    tracks: list[Track],
    polygon: Polygon,
    mode: str = "inside",
) -> list[Track]:
```

**Modes (Phase 1 = `inside` only):**
- `inside`: Keep detections where bbox center is inside the polygon. Tracks with no remaining detections are dropped.

**Additional filters:**
- `filter_by_min_frames(tracks, min_frames)` — drop short tracks
- `filter_by_confidence(tracks, min_confidence)` — drop low-confidence detections

**Files created:**
- `backend/app/pipeline/__init__.py`
- `backend/app/pipeline/filters.py`

**Verification (unit test style):**
```python
# Synthetic test: create a polygon and detections with known positions
# Assert detections inside polygon are kept, outside are dropped
```

---

## Step 1d: Metric — `dwell_count`

**What:** For each track, compute how long its center point stays inside the ROI. Emit events for tracks that dwell >= threshold.

**Function:**

```python
def compute_dwell_count(
    tracks: list[Track],
    params: dict,
    roi_polygon: list[dict] | None,
    fps: float,
    video_duration: float,
) -> dict:
```

**Params:**
- `dwell_threshold_seconds` (float, default 5.0): Minimum seconds inside ROI to count as "dwelling"
- `jitter_tolerance_px` (int, default 15): Ignore brief exits near polygon edge (Phase 1: not implemented, placeholder)

**Returns:**
```json
{
  "events": [
    {
      "type": "dwell",
      "track_id": 7,
      "start_time_sec": 12.3,
      "end_time_sec": 18.1,
      "duration_sec": 5.8,
      "frame_start": 369,
      "frame_end": 543
    }
  ],
  "aggregates": {
    "total_dwellers": 14,
    "average_dwell_seconds": 8.2,
    "max_dwell_seconds": 23.4,
    "min_dwell_seconds": 5.1
  }
}
```

**Logic:**
1. For each track, iterate detections and check if bbox center is inside ROI polygon
2. Find contiguous runs of "inside" frames
3. Convert frame runs to time using fps
4. Keep runs where duration >= threshold
5. Build events list + aggregates (total count, average, min, max)

**Files created:**
- `backend/app/metrics/__init__.py`
- `backend/app/metrics/dwell.py`

**Verification:**
```python
# Unit test with synthetic tracks and a known polygon:
# Track A: 10s inside ROI (threshold=5 → event)
# Track B: 3s inside ROI (threshold=5 → no event)
# Assert: 1 event, total_dwellers=1
```

---

## Step 1e: Pipeline Runner

**What:** Orchestrate the full pipeline: decode → vision → filter → metric. Accept a hardcoded plan dict.

**Function:**

```python
async def run_pipeline(
    video_path: str,
    plan: dict,
    roi_polygon: list[dict] | None,
) -> dict:
```

**Pipeline steps:**
1. **Decode:** Extract video metadata (fps, frame_count, duration) using existing `extract_metadata()`
2. **Vision:** Run YOLO detection + tracking → `list[Track]`
3. **Filter:** If `use_roi` and ROI exists, apply ROI filter (mode=inside)
4. **Metric:** Look up task in registry, call with filtered tracks
5. **Return:** `{ "events": [...], "aggregates": {...}, "metadata": {...} }`

**Task registry (Phase 1 — only `dwell_count`):**

```python
TASK_REGISTRY = {
    "dwell_count": compute_dwell_count,
}
```

**Files created:**
- `backend/app/pipeline/runner.py`
- `backend/app/pipeline/registry.py`

---

## Step 1f: API Endpoint — `POST /api/video/{id}/analyze`

**What:** New endpoint that accepts a hardcoded plan, loads the ROI, runs the pipeline, and returns results.

**Request body:**
```json
{
  "plan": {
    "task": "dwell_count",
    "object": "person",
    "use_roi": true,
    "params": {
      "dwell_threshold_seconds": 10
    }
  }
}
```

**Response (success):**
```json
{
  "status": "ok",
  "plan": { "...the plan..." },
  "result": {
    "events": [...],
    "aggregates": {...},
    "metadata": {
      "frames_processed": 1800,
      "tracks_found": 47,
      "tracks_after_filter": 14,
      "processing_time_sec": 12.3,
      "model_used": "yolo11n",
      "video_duration_sec": 60.0
    }
  }
}
```

**Response (needs ROI):**
```json
{
  "status": "needs_roi",
  "plan": { "...the plan..." },
  "message": "This analysis needs a region of interest. Draw one on the video, then run again."
}
```

**Files changed:**
- `backend/app/main.py` — add new endpoint + `AnalyzeRequest` model

---

## File Tree After Phase 1

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # + POST /api/video/{id}/analyze
│   ├── core/
│   │   ├── __init__.py
│   │   └── decode.py               # (unchanged)
│   ├── vision/
│   │   ├── __init__.py             # NEW
│   │   ├── models.py               # NEW — BBox, Detection, Track
│   │   └── detector.py             # NEW — YOLO detect + track
│   ├── pipeline/
│   │   ├── __init__.py             # NEW
│   │   ├── runner.py               # NEW — orchestrates pipeline
│   │   ├── registry.py             # NEW — TASK_REGISTRY
│   │   └── filters.py              # NEW — ROI, quality filters
│   ├── metrics/
│   │   ├── __init__.py             # NEW
│   │   └── dwell.py                # NEW — dwell_count metric
│   └── storage/
│       └── roi_storage.json
├── uploads/
├── requirements.txt                # + ultralytics, shapely
└── README.md
```

---

## Checkpoint

After implementing all steps, the following E2E flow should work:

1. Upload a video via the frontend
2. Draw an ROI on the video
3. `curl -X POST http://localhost:8000/api/video/{id}/analyze -H 'Content-Type: application/json' -d '{"plan": {"task": "dwell_count", "object": "person", "use_roi": true, "params": {"dwell_threshold_seconds": 5}}}'`
4. Get back real dwell events and aggregate counts
5. Without an ROI, get back `{"status": "needs_roi", ...}`

**Then** consider small flexibility: make `dwell_threshold_seconds` configurable in the plan and verify different thresholds yield different results.
