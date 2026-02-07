# Phase 1 Walkthrough — Understanding Every File

This document walks you through every file that was created or modified in Phase 1, in the exact order that data flows through the pipeline. By the end you should understand what every object is, what it contains, how each file connects to the next, and what the final output looks like.

---

## Table of Contents

1. [The Big Picture](#1-the-big-picture)
2. [What Gets Sent In — The Request](#2-what-gets-sent-in--the-request)
3. [File-by-File Walkthrough (In Pipeline Order)](#3-file-by-file-walkthrough-in-pipeline-order)
   - [File 1: `main.py` — The front door](#file-1-mainpy--the-front-door)
   - [File 2: `runner.py` — The conductor](#file-2-runnerpy--the-conductor)
   - [File 3: `decode.py` — Step 1: Read the video](#file-3-decodepy--step-1-read-the-video)
   - [File 4: `models.py` — The shared vocabulary](#file-4-modelspy--the-shared-vocabulary)
   - [File 5: `detector.py` — Step 2: Find and track people](#file-5-detectorpy--step-2-find-and-track-people)
   - [File 6: `filters.py` — Step 3: Keep only what's in the ROI](#file-6-filterspy--step-3-keep-only-whats-in-the-roi)
   - [File 7: `registry.py` — The task lookup table](#file-7-registrypy--the-task-lookup-table)
   - [File 8: `dwell.py` — Step 4: Compute the dwell metric](#file-8-dwellpy--step-4-compute-the-dwell-metric)
4. [What Comes Back — The Response](#4-what-comes-back--the-response)
5. [Supporting Files](#5-supporting-files)
6. [Complete File Inventory](#6-complete-file-inventory)

---

## 1. The Big Picture

Phase 1 answers one question: **"Can we take a video, run YOLO on it, filter by the user's drawn ROI, and compute a dwell metric — all triggered by a single API call?"**

Here is the entire pipeline as a picture:

```
YOU (or curl / frontend)
  │
  │  POST /api/video/{id}/analyze
  │  Body: { "plan": { "task": "dwell_count", "object": "person", "use_roi": true, ... } }
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  main.py  —  THE FRONT DOOR                                         │
│                                                                      │
│  1. Does the video file exist?               → 404 if not           │
│  2. Is the task name valid?                  → 400 if not           │
│  3. Does the plan need an ROI?                                       │
│     - Yes, and ROI exists   → load the polygon, continue            │
│     - Yes, but no ROI saved → return {"status": "needs_roi"}, stop  │
│     - No                    → continue without polygon              │
│  4. Hand everything to the runner ↓                                  │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  runner.py  —  THE CONDUCTOR                                         │
│                                                                      │
│  Reads the plan dict and calls four steps in order:                  │
│                                                                      │
│  STEP 1 ─ decode.py ─── "What video is this?"                       │
│  │  Input:  video file path                                          │
│  │  Output: { fps: 59.94, frame_count: 1198, duration: 19.99, ... } │
│  │                                                                   │
│  STEP 2 ─ detector.py ─── "Where are the people?"                   │
│  │  Input:  video file path + config (model, classes, confidence)    │
│  │  Output: list[Track]  ← e.g. 45 Track objects                    │
│  │                                                                   │
│  STEP 3 ─ filters.py ─── "Which people are inside the ROI?"         │
│  │  Input:  list[Track] + ROI polygon                                │
│  │  Output: list[Track]  ← e.g. 4 Track objects (only in ROI)       │
│  │                                                                   │
│  STEP 4 ─ dwell.py ─── "How long did each person stay?"             │
│  │  Input:  filtered list[Track] + ROI polygon + params (threshold)  │
│  │  Output: { events: [...], aggregates: {...} }                     │
│  │                                                                   │
│  Finally: attach metadata (processing time, counts, etc.) and return │
└──────────────────────────────────────────────────────────────────────┘
```

**The key insight:** The pipeline always flows `Decode → Vision → Filter → Metric`. Steps 1 and 2 are the same no matter what metric you run. Steps 3 and 4 change based on the plan. This means when we add `traffic_count` or `occupancy` later, we only write a new metric function — the vision and filter layers stay the same.

---

## 2. What Gets Sent In — The Request

When you call the analyze endpoint (via curl, Postman, or the frontend), you send a JSON body like this:

```json
{
  "plan": {
    "task": "dwell_count",
    "object": "person",
    "use_roi": true,
    "params": {
      "dwell_threshold_seconds": 5
    }
  }
}
```

What each field means:

| Field | What it does |
|-------|-------------|
| `task` | Which metric function to run. Currently only `"dwell_count"` exists. This string is used to look up the function in the registry. |
| `object` | What to detect in the video. `"person"` tells YOLO to only look for people (YOLO can detect 80 object types — cars, dogs, phones, etc. — but we only want people). |
| `use_roi` | `true` = filter detections to only those inside the user-drawn polygon. `false` = analyze the whole frame. |
| `params` | Settings specific to the chosen metric. For `dwell_count`, the key param is `dwell_threshold_seconds` — how long someone must stay in the ROI to count as "dwelling." |

This plan dict is what flows through the entire pipeline. The runner reads it, pulls out the config for each step, and passes the right values to the right functions.

---

## 3. File-by-File Walkthrough (In Pipeline Order)

---

### File 1: `main.py` — The front door

**Path:** `backend/app/main.py`
**Status:** MODIFIED (was already there; new code added)

This is the FastAPI server. It already had endpoints for uploading videos, getting metadata, streaming video, and saving/loading ROI polygons. Phase 1 added three things:

**Addition 1 — New imports (lines 19-20):**
```python
from app.pipeline.runner import run_pipeline
from app.pipeline.registry import get_available_tasks
```
These bring in the pipeline runner (the conductor that orchestrates everything) and the function that returns the list of valid task names (used for validation).

**Addition 2 — `AnalyzeRequest` model (lines 36-39):**
```python
class AnalyzeRequest(BaseModel):
    plan: dict
```
This is a Pydantic model that defines the shape of the request body. It simply says: "the request must have a `plan` field that is a dictionary." FastAPI uses this to automatically parse and validate incoming JSON.

**Addition 3 — The `/analyze` endpoint (lines 257-338):**

This is the new endpoint: `POST /api/video/{video_id}/analyze`. It does three things before handing off to the pipeline:

1. **Validates the video exists** (lines 288-290) — Checks that `uploads/{video_id}.mp4` is a real file.

2. **Validates the task name** (lines 293-299) — Asks the registry "what tasks do you know?" and checks that the plan's task is one of them. Right now, the only valid task is `"dwell_count"`.

3. **Handles the ROI** (lines 301-317) — This is the `needs_roi` logic from Section 5.6 of the PIPELINE-LOGIC doc. If the plan says `use_roi: true`:
   - It loads `roi_storage.json` and looks for a saved polygon for this video.
   - If a polygon exists, it grabs it and continues.
   - If no polygon exists, it **stops** and returns a helpful response telling the frontend to prompt the user to draw one:
     ```json
     {
       "status": "needs_roi",
       "plan": { ... },
       "roi_instruction": "Draw a region of interest around the area you want to analyze.",
       "message": "This analysis needs a region of interest. Draw one on the video, then run again."
     }
     ```
   - The pipeline does NOT run. The user must draw an ROI first.

4. **Calls the pipeline** (lines 320-326) — If all checks pass, it calls `run_pipeline()` with the video path, the plan dict, and the ROI polygon (or `None`).

---

### File 2: `runner.py` — The conductor

**Path:** `backend/app/pipeline/runner.py`
**Status:** NEW

This is the orchestrator. It has one function: `run_pipeline()`. Think of it as a foreman on a construction site — it doesn't do the work itself, it calls each specialist in order and passes results between them.

**What it receives:**
```python
async def run_pipeline(video_path: str, plan: dict, roi_polygon: list[dict] | None) -> dict
```
- `video_path` — where the video file is on disk (e.g. `"uploads/abc123.mp4"`)
- `plan` — the plan dict from the request (task, object, params, etc.)
- `roi_polygon` — the list of `{"x": ..., "y": ...}` points, or `None` if no ROI

**What it does with the plan (lines 47-66):**

Before calling any step, the runner unpacks the plan dict into individual variables with sensible defaults:

```
plan.task             → task_name        (default: "dwell_count")
plan.use_roi          → use_roi          (default: true)
plan.params           → params           (default: {})
plan.vision.model     → model_name       (default: "yolo11n.pt")
plan.vision.detect_classes → detect_classes (default: [plan.object] = ["person"])
plan.vision.confidence_threshold → confidence (default: 0.4)
plan.filters.roi_mode → roi_mode         (default: "inside")
plan.filters.min_track_frames → min_track_frames (default: 5)
```

This means the simplest possible plan — `{"task": "dwell_count", "object": "person", "use_roi": true, "params": {}}` — works fine because every other setting has a default.

**Then it calls the four steps in order:**

- **Step 1:** `extract_metadata(video_path)` → gets fps, frame_count, duration
- **Step 2:** `run_detection_and_tracking(video_path, ...)` → gets `list[Track]`
- **Step 3:** `apply_filters(tracks, roi_polygon, ...)` → gets filtered `list[Track]`
- **Step 4:** `TASK_REGISTRY[task_name](filtered_tracks, params, ...)` → gets events + aggregates

Finally it attaches a `metadata` dict with processing stats (how many tracks were found, how many survived filtering, how long it took, etc.) and returns everything.

---

### File 3: `decode.py` — Step 1: Read the video

**Path:** `backend/app/core/decode.py`
**Status:** UNCHANGED (already existed before Phase 1)

This file was already built when you set up video upload. It has one function:

```python
def extract_metadata(video_path: str) -> dict
```

It uses OpenCV to open the video file and read its properties:

```python
{
    "fps": 59.94,          # frames per second
    "frame_count": 1198,   # total frames in the video
    "width": 3840,         # video width in pixels
    "height": 2160,        # video height in pixels
    "duration": 19.99      # video length in seconds
}
```

The runner needs `fps` (to convert frame numbers to timestamps) and `duration` (to pass to the metric function). This step is fast — it just reads header info, it doesn't process any frames.

---

### File 4: `models.py` — The shared vocabulary

**Path:** `backend/app/vision/models.py`
**Status:** NEW

This file defines three Pydantic classes that every other file uses. These are the "objects" that data gets packaged into as it flows through the pipeline. Think of them as containers that everyone agreed to use.

#### Object 1: `BBox` (Bounding Box)

```
BBox
├── x1: float    ← left edge (pixels)
├── y1: float    ← top edge (pixels)
├── x2: float    ← right edge (pixels)
├── y2: float    ← bottom edge (pixels)
├── .center      ← computed: ((x1+x2)/2, (y1+y2)/2)  ← THE KEY PROPERTY
├── .width       ← computed: x2 - x1
└── .height      ← computed: y2 - y1
```

A `BBox` is a rectangle drawn around a detected person in one frame. YOLO outputs these in `(x1, y1, x2, y2)` format — top-left corner and bottom-right corner. The `.center` property is crucial because that's what we use to check if a person is inside the ROI polygon.

**Concrete example:**
```
BBox(x1=100, y1=200, x2=150, y2=350)
  → This is a box 50px wide and 150px tall
  → Its center is at (125, 275)
  → We ask: is the point (125, 275) inside the ROI polygon?
```

#### Object 2: `Detection` (One sighting in one frame)

```
Detection
├── frame_index: int        ← which frame number (e.g. 354)
├── timestamp_sec: float    ← when in the video (e.g. 5.91 seconds)
├── bbox: BBox              ← the rectangle around the person
├── class_name: str         ← what was detected (e.g. "person")
├── confidence: float       ← how sure YOLO is (e.g. 0.87 = 87%)
└── track_id: int | None    ← which tracked person this belongs to (e.g. 7)
```

A `Detection` is one sighting of one object in one frame. If YOLO sees 5 people in frame 100, that's 5 separate Detection objects, each with a different `track_id` and `bbox`.

**Concrete example:**
```
Detection(
    frame_index=354,
    timestamp_sec=5.91,
    bbox=BBox(x1=2300, y1=950, x2=2350, y2=1100),
    class_name="person",
    confidence=0.87,
    track_id=70
)
```
This means: "In frame 354 (at 5.91 seconds into the video), YOLO found a person with 87% confidence in a box from (2300,950) to (2350,1100), and this person is being tracked as person #70."

#### Object 3: `Track` (One person across the entire video)

```
Track
├── track_id: int                ← unique ID for this person (e.g. 70)
├── class_name: str              ← what they are (e.g. "person")
├── detections: list[Detection]  ← every frame they appeared in, sorted by time
├── .start_time                  ← computed: first detection's timestamp
├── .end_time                    ← computed: last detection's timestamp
├── .duration                    ← computed: end_time - start_time
└── .frame_count                 ← computed: how many detections
```

A `Track` groups all the Detections that belong to the same physical person. YOLO's built-in ByteTrack tracker assigns a consistent `track_id` to the same person across frames — so if person #70 appears in frames 354 through 404, that's one Track with 51 Detections inside it.

**Concrete example:**
```
Track(
    track_id=70,
    class_name="person",
    detections=[
        Detection(frame_index=354, timestamp_sec=5.91, bbox=..., confidence=0.87, track_id=70),
        Detection(frame_index=355, timestamp_sec=5.92, bbox=..., confidence=0.85, track_id=70),
        Detection(frame_index=356, timestamp_sec=5.93, bbox=..., confidence=0.89, track_id=70),
        ... 48 more ...
        Detection(frame_index=404, timestamp_sec=6.74, bbox=..., confidence=0.82, track_id=70),
    ]
)
  → This person was seen for 51 frames (0.85 seconds)
  → They first appeared at 5.91s and last appeared at 6.74s
```

**How these three objects nest:**

```
list[Track]                          ← the full output of the vision step
  └── Track                          ← one person across the whole video
        ├── track_id: 70
        └── detections:
              ├── Detection          ← person 70 in frame 354
              │     ├── bbox: BBox   ← their rectangle in that frame
              │     └── ...
              ├── Detection          ← person 70 in frame 355
              │     ├── bbox: BBox
              │     └── ...
              └── ... (more frames)
```

Everything downstream — filters and metrics — works with `list[Track]`. Filters remove Tracks or remove Detections within Tracks. Metrics iterate over Tracks and their Detections to compute results.

---

### File 5: `detector.py` — Step 2: Find and track people

**Path:** `backend/app/vision/detector.py`
**Status:** NEW

This is the most computationally expensive file. It wraps the Ultralytics YOLO library and is the only file that talks to YOLO directly. Its job: take a video file in, return `list[Track]` out.

**The one public function:**
```python
def run_detection_and_tracking(
    video_path: str,
    model_name: str = "yolo11n.pt",
    detect_classes: list[str] | None = None,
    confidence: float = 0.4,
    sample_fps: float | None = None,
) -> list[Track]
```

**How it works, step by step:**

**Step A — Load the model (line 69):**
```python
model = _get_model(model_name)
```
This calls a helper that loads the YOLO model file (e.g. `yolo11n.pt`). On the very first call, this downloads the model file from the internet (~6MB). After that, the model stays cached in memory (`_model_cache` dict on line 25) so subsequent calls are instant.

**Step B — Figure out class filtering (lines 72-77):**

YOLO knows 80 object types (person, car, dog, cell phone, dining table, etc.). Each has a numeric ID. When the plan says `"object": "person"`, this code converts `"person"` to YOLO's internal class ID `0`. The `_class_name_to_ids()` helper (line 37) does this lookup using the model's built-in `model.names` dictionary.

**Step C — Get the video's FPS (lines 80-87):**

Opens the video with OpenCV just to read its frame rate. This is needed to calculate timestamps: `timestamp = frame_index / fps`. For example, frame 354 in a 59.94fps video = 5.91 seconds.

**Step D — Run YOLO tracking (lines 93-154):**

This is the core loop. It calls `model.track()` which streams through the video frame by frame:

```python
for result in model.track(source=video_path, persist=True, stream=True, ...):
```

Key arguments:
- `source=video_path` — the video file to process
- `persist=True` — **critical** — this tells YOLO to maintain consistent track IDs across frames. Without this, the same person could get a different ID in every frame.
- `stream=True` — process one frame at a time instead of loading the whole video into memory
- `conf=0.4` — ignore detections below 40% confidence
- `classes=[0]` — only detect "person" (class ID 0)

For each frame, YOLO returns a `result` object. The code extracts:
- `result.boxes.xyxy[i]` — the bounding box coordinates for detection `i`
- `result.boxes.conf[i]` — the confidence score
- `result.boxes.cls[i]` — the class ID (0 = person)
- `result.boxes.id[i]` — the track ID assigned by ByteTrack

Each detection gets packaged into a `Detection` object and stored in a dictionary keyed by `track_id`:

```python
tracks_dict[track_id].append(detection)
```

So after processing all frames, `tracks_dict` might look like:
```
{
    70: [Detection(frame=354, ...), Detection(frame=355, ...), ... Detection(frame=404, ...)],
    71: [Detection(frame=69, ...),  Detection(frame=70, ...),  ... Detection(frame=169, ...)],
    72: [Detection(frame=618, ...), Detection(frame=619, ...), ... Detection(frame=646, ...)],
    ...45 total entries...
}
```

**Step E — Build Track objects (lines 156-166):**

Finally, the dictionary gets converted into a sorted list of `Track` objects:

```python
for track_id, detections in sorted(tracks_dict.items()):
    tracks.append(Track(track_id=track_id, class_name="person", detections=detections))
```

**What comes out:** A `list[Track]` — in our test, 45 Track objects representing 45 distinct people seen in the 20-second video.

---

### File 6: `filters.py` — Step 3: Keep only what's in the ROI

**Path:** `backend/app/pipeline/filters.py`
**Status:** NEW

This file takes the full `list[Track]` from the detector and narrows it down. It contains four functions, three individual filters and one convenience wrapper.

**The convenience wrapper the runner calls:**
```python
def apply_filters(tracks, roi_polygon, roi_mode, min_track_frames, min_confidence) -> list[Track]
```

It runs filters in a fixed sequence:

**Filter 1 — `filter_by_min_frames(tracks, min_frames=5)`**

Drops any Track with fewer than 5 detections. If YOLO briefly misidentified a shadow as a person for 2 frames, that Track gets thrown out. This is a quality gate — real people will appear in many frames.

**Filter 2 — `filter_by_confidence(tracks, min_confidence=0.4)`**

Goes inside each Track and removes individual Detections where YOLO's confidence was below 40%. If a Track loses all its Detections this way, the whole Track is dropped. This ensures we're only working with detections YOLO was reasonably sure about.

**Filter 3 — `filter_tracks_by_roi(tracks, polygon, mode="inside")`**

This is the spatial filter — the one that uses the user-drawn ROI polygon. For each Detection in each Track:

1. Get the detection's bbox center: `center_x, center_y = det.bbox.center`
2. Create a Shapely Point: `point = Point(center_x, center_y)`
3. Ask Shapely: `polygon.contains(point)` — is this point inside the ROI polygon?
4. If yes (and mode is "inside"), keep the detection. If no, discard it.

After checking all detections, if a Track has zero surviving detections, the whole Track is dropped.

**How the polygon is built (line 127):**

The ROI polygon comes from the frontend as a list of dicts: `[{"x": 2291, "y": 909}, {"x": 2296, "y": 1542}, ...]`. The code converts this into a Shapely Polygon object:
```python
polygon = Polygon([(p["x"], p["y"]) for p in roi_polygon])
```
Shapely then handles all the geometry math (point-in-polygon testing) internally.

**Concrete example of filtering:**

```
Before filtering:  45 tracks (all people in the video)
After min_frames:  42 tracks (3 fleeting tracks dropped)
After confidence:  42 tracks (none dropped — YOLO was confident)
After ROI filter:  4 tracks  (only 4 people walked through the narrow ROI polygon)
```

---

### File 7: `registry.py` — The task lookup table

**Path:** `backend/app/pipeline/registry.py`
**Status:** NEW

This is the simplest file. It's a dictionary that maps task name strings to Python functions:

```python
TASK_REGISTRY = {
    "dwell_count": compute_dwell_count,
}
```

When the runner needs to run a metric, it does:
```python
task_fn = TASK_REGISTRY["dwell_count"]  # gets the compute_dwell_count function
result = task_fn(tracks, params, ...)   # calls it
```

Right now there's only one entry. In Phase 3, when you add more metrics, you'll add lines like:
```python
"traffic_count": compute_traffic_count,
"occupancy": compute_occupancy,
```

The registry also provides `get_available_tasks()` which returns `["dwell_count"]` — this is used by `main.py` to validate that the task name in the plan is valid.

---

### File 8: `dwell.py` — Step 4: Compute the dwell metric

**Path:** `backend/app/metrics/dwell.py`
**Status:** NEW

This file answers the question: **"For each person inside the ROI, how long did they stay there?"**

It has one public function:
```python
def compute_dwell_count(tracks, params, roi_polygon, fps, video_duration) -> dict
```

**What it receives:**
- `tracks` — the filtered list of Tracks (only people who were in the ROI)
- `params` — task-specific settings from the plan, mainly `dwell_threshold_seconds`
- `roi_polygon` — the ROI polygon points (used for precise per-frame in/out checking)
- `fps` — frames per second (to convert frame counts to seconds)
- `video_duration` — total video length

**How it works, step by step:**

**Step A — For each Track, find which frames are "inside" (lines 91-100):**

Even though the tracks were already filtered by the ROI in Step 3, the dwell metric re-checks each detection against the polygon. Why? Because Step 3's filter might have kept a Track that was *partially* inside the ROI (it entered and exited). The dwell metric needs to know the exact frames where the person was inside to measure timing precisely.

```python
for track in tracks:
    inside_frames = []
    for det in track.detections:
        center_x, center_y = det.bbox.center
        if polygon.contains(Point(center_x, center_y)):
            inside_frames.append(det.frame_index)
```

For Track #70, this might produce: `inside_frames = [354, 355, 356, ..., 404]`

**Step B — Find contiguous runs (lines 102-103):**

The helper function `_find_contiguous_runs()` groups consecutive frame numbers into runs. This handles the case where a person enters the ROI, leaves, and comes back — that would be two separate dwell events, not one long one.

```
Input:  [354, 355, 356, 357, ..., 404, 414, 415]
Output: [(354, 404), (414, 415)]
         ↑ first run: frames 354-404        ↑ second run: frames 414-415
```

The function allows a gap of up to 2 frames between consecutive numbers (line 38). This accounts for occasional frames where YOLO missed the person briefly.

**Step C — Convert runs to durations and check threshold (lines 105-120):**

For each run:
```python
num_frames = run_end - run_start + 1  # e.g. 404 - 354 + 1 = 51 frames
duration = num_frames / fps           # e.g. 51 / 59.94 = 0.85 seconds
```

If `duration >= dwell_threshold_seconds` (e.g. >= 5.0), it becomes a dwell event:
```python
{
    "type": "dwell",
    "track_id": 70,
    "start_time_sec": 5.91,
    "end_time_sec": 6.74,
    "duration_sec": 0.85,
    "frame_start": 354,
    "frame_end": 404
}
```

If the duration is less than the threshold, the run is discarded — the person didn't "dwell" long enough.

**Step D — Compute aggregates (lines 122-140):**

After processing all tracks, the function computes summary stats:
```python
{
    "total_dwellers": 4,           # how many unique people dwelled
    "total_dwell_events": 8,       # total dwell events (one person can have multiple)
    "average_dwell_seconds": 0.29, # average duration
    "max_dwell_seconds": 0.85,     # longest dwell
    "min_dwell_seconds": 0.03      # shortest dwell
}
```

**What it returns:**
```python
{
    "events": [ ... list of dwell event dicts ... ],
    "aggregates": { ... summary stats dict ... }
}
```

---

## 4. What Comes Back — The Response

After the pipeline finishes, the runner attaches metadata and `main.py` wraps everything in a response. Here's what the final JSON response looks like:

```json
{
  "status": "ok",
  "plan": {
    "task": "dwell_count",
    "object": "person",
    "use_roi": true,
    "params": { "dwell_threshold_seconds": 0 }
  },
  "result": {
    "events": [
      {
        "type": "dwell",
        "track_id": 70,
        "start_time_sec": 5.91,
        "end_time_sec": 6.74,
        "duration_sec": 0.85,
        "frame_start": 354,
        "frame_end": 404
      },
      {
        "type": "dwell",
        "track_id": 71,
        "start_time_sec": 1.15,
        "end_time_sec": 1.67,
        "duration_sec": 0.53,
        "frame_start": 69,
        "frame_end": 100
      }
    ],
    "aggregates": {
      "total_dwellers": 4,
      "total_dwell_events": 8,
      "average_dwell_seconds": 0.29,
      "max_dwell_seconds": 0.85,
      "min_dwell_seconds": 0.03
    },
    "metadata": {
      "frames_processed": 1198,
      "tracks_found": 45,
      "tracks_after_filter": 4,
      "processing_time_sec": 65.67,
      "model_used": "yolo11n.pt",
      "video_fps": 59.94,
      "video_duration_sec": 19.99,
      "task": "dwell_count"
    }
  }
}
```

Reading this you can see:
- **events** — each dwell event tells you which person (`track_id`), when they started and stopped (`start_time_sec`, `end_time_sec`), how long they stayed (`duration_sec`), and the exact frame numbers. In the future, clicking an event could jump the video to that timestamp.
- **aggregates** — headline numbers: 4 people dwelled, average 0.29s, longest 0.85s.
- **metadata** — diagnostic info: 1198 frames processed, 45 people tracked total, 4 survived the ROI filter, the whole thing took 65.67 seconds.

---

## 5. Supporting Files

These files don't contain pipeline logic but are required for things to work:

### `backend/requirements.txt` (MODIFIED)

**What changed:** Two new lines added at the bottom:
```
ultralytics>=8.3.0   # YOLO detection, tracking, and pose
shapely>=2.0.0       # Polygon geometry for ROI point-in-polygon
```

- **ultralytics** — the Python package that provides the YOLO models. When you call `from ultralytics import YOLO` and then `YOLO("yolo11n.pt")`, this package downloads the model weights, loads them, and gives you a `.track()` method that processes video.
- **shapely** — a geometry library. We use exactly two things from it: `Polygon` (to represent the ROI) and `Point` (to represent a bbox center). Then we call `polygon.contains(point)` to check if the point is inside.

### `backend/app/vision/__init__.py` (NEW)

One line: `# Vision module — YOLO detection, tracking, and data models`

This is a Python package marker. Without it, Python can't do `from app.vision.models import Track`. The `__init__.py` file tells Python "this folder is a package you can import from." It has no logic.

### `backend/app/pipeline/__init__.py` (NEW)

One line: `# Pipeline module — runner, filters, and task registry`

Same thing — package marker for the `pipeline` folder.

### `backend/app/metrics/__init__.py` (NEW)

One line: `# Metrics module — metric computation functions (dwell, traffic, etc.)`

Same thing — package marker for the `metrics` folder.

---

## 6. Complete File Inventory

Every file created or modified in Phase 1, at a glance:

| # | File | Status | What it does |
|---|------|--------|-------------|
| 1 | `backend/requirements.txt` | MODIFIED | Added `ultralytics` and `shapely` dependencies |
| 2 | `backend/app/main.py` | MODIFIED | Added `AnalyzeRequest` model + `POST /analyze` endpoint |
| 3 | `backend/app/vision/__init__.py` | NEW | Package marker (1 line) |
| 4 | `backend/app/vision/models.py` | NEW | Defines `BBox`, `Detection`, `Track` — the shared data structures |
| 5 | `backend/app/vision/detector.py` | NEW | Wraps YOLO `.track()` → returns `list[Track]` |
| 6 | `backend/app/pipeline/__init__.py` | NEW | Package marker (1 line) |
| 7 | `backend/app/pipeline/runner.py` | NEW | Orchestrates Decode → Vision → Filter → Metric |
| 8 | `backend/app/pipeline/registry.py` | NEW | Maps task name strings to metric functions |
| 9 | `backend/app/pipeline/filters.py` | NEW | ROI point-in-polygon filter + quality filters |
| 10 | `backend/app/metrics/__init__.py` | NEW | Package marker (1 line) |
| 11 | `backend/app/metrics/dwell.py` | NEW | `dwell_count` metric — computes dwell events + aggregates |

**Unchanged files that the pipeline uses:**
- `backend/app/core/decode.py` — video metadata extraction (already existed)
- `backend/app/storage/roi_storage.json` — saved ROI polygons (already existed)

**Folder structure after Phase 1:**
```
backend/app/
├── __init__.py
├── main.py                  ← MODIFIED (added /analyze endpoint)
├── core/
│   ├── __init__.py
│   └── decode.py            ← unchanged, used by Step 1
├── vision/                  ← NEW FOLDER
│   ├── __init__.py          ← new (package marker)
│   ├── models.py            ← new (BBox, Detection, Track)
│   └── detector.py          ← new (YOLO wrapper)
├── pipeline/                ← NEW FOLDER
│   ├── __init__.py          ← new (package marker)
│   ├── runner.py            ← new (orchestrator)
│   ├── registry.py          ← new (task lookup table)
│   └── filters.py           ← new (ROI + quality filters)
├── metrics/                 ← NEW FOLDER
│   ├── __init__.py          ← new (package marker)
│   └── dwell.py             ← new (dwell_count metric)
└── storage/
    └── roi_storage.json     ← unchanged, stores ROI polygons
```
