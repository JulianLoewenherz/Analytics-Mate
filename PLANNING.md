# Videometric — Planning Document

This doc defines the MVP scope, tech stack, logic structure, and build order for “Cursor for video analytics.”

---

## 1. Product Definition

**One sentence:** An AI-assisted workspace that lets users ask natural-language questions about video and iteratively build, inspect, and refine the logic used to answer them—backed by visual evidence.

**Differentiator:** Metric = generated on demand. Pipeline = assembled dynamically. Logic = inspectable and editable. Not predefined dashboards or opaque CV pipelines.

---

## 2. MVP Feature List

### A. Core Workflow (Must-Have)

| # | Feature | Description |
|---|---------|-------------|
| 1 | **Video input** | Upload or select a video; local processing only. |
| 2 | **Natural-language question** | User asks in plain English (e.g. “How many people dwell outside my store?”). |
| 3 | **Editable analysis plan** | AI produces a plan (not raw code by default). User sees human-readable steps and parameters. |
| 4 | **ROI drawing** | User draws a region of interest (e.g. sidewalk zone) on a frame. |
| 5 | **Run plan + evidence** | After running: annotated video preview (boxes + tracks), results panel (counts, dwell events, basic timeline). |
| 6 | **Edit parameters** | Sliders/inputs for dwell threshold (seconds), confidence threshold, min track length, etc. |
| 7 | **Re-run and compare** | Re-run after edits; at least “latest vs previous run” for comparison. |

**MVP loop:** Intent → Plan → Evidence → Tweak → Re-run.

### B. Trust + Debugging (High Leverage, Still MVP)

| # | Feature | Description |
|---|---------|-------------|
| 8 | **Step-by-step run mode** | Run “detect only” → “track” → “dwell” → “aggregate” independently. |
| 9 | **Event explorer** | List of dwell events (start time, end time, duration, track id). Clicking an event jumps video to that timestamp. |

### C. Explicitly Out of MVP (For Now)

- Multi-camera  
- People attributes (age/gender) — privacy and complexity  
- Cloud processing  
- Complex query types (e.g. “facing storefront”) — would need pose/heading  

---

## 3. Underlying Tech Stack

### Backend (Video + CV)

| Component | Choice | Role |
|-----------|--------|------|
| Language | Python | Glue + CV + API |
| Detection | YOLOv8 / YOLOv11 (Ultralytics) | Person detection |
| Tracking | ByteTrack (or DeepSORT) | Track IDs across frames |
| Video I/O | OpenCV | Decode/encode, drawing overlays |
| Math | NumPy | Computations |

### Frontend

- **Option A (shortest path):** Streamlit — single stack, fast MVP.  
- **Option B (product feel):** Next.js + FastAPI — more work, better UX later.

**Recommendation for shipping fast:** Streamlit + Python-only backend.

### AI (Planning Only)

- LLM is used **only** to produce a **structured plan (JSON)** from the user prompt.  
- **No** execution of arbitrary code from the model.  
- Plan is validated against a schema and mapped to known metric modules.

---

## 4. Logic Structure (Modular, Testable)

Four deterministic stages. Each has a clear input/output contract so you can test after every step.

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Decode    │ →  │   Detect    │ →  │   Track     │ →  │   Metric    │
│ video path  │    │   frames    │    │  detections │    │ tracks+ROI  │
│     ↓       │    │     ↓       │    │     ↓       │    │     ↓       │
│ frames, fps │    │ per-frame   │    │ track IDs   │    │ events +    │
│ frame size  │    │ detections  │    │ over time   │    │ aggregates  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Stage 1: Decode

- **Input:** Video path  
- **Output:** Frames iterator (or list), fps, frame size  

### Stage 2: Detect

- **Input:** Frames  
- **Output:** Per-frame detections, e.g.  
  `[{ frame: 120, boxes: [{ x1, y1, x2, y2, conf, cls: "person" }] }]`

### Stage 3: Track

- **Input:** Detections  
- **Output:** Tracks over time, e.g.  
  `[{ track_id: 7, frame: 120, box: ..., conf: ... }, ...]`

### Stage 4: Metric (Rules)

- **Input:** Tracks + ROI + parameters  
- **Output:**  
  - **Events:** e.g. “track 7 dwelled from t=12.3s to 18.1s”  
  - **Aggregates:** e.g. “total dwellers = 14”  

The AI selects **which** metric module runs and **with what params**. The modules themselves are fixed and safe.

---

## 5. Plan Format (AI → Safe Execution)

The LLM outputs a JSON plan, for example:

```json
{
  "task": "dwell_count",
  "object": "person",
  "roi": "storefront_zone",
  "params": {
    "dwell_seconds": 5,
    "min_conf": 0.4,
    "min_track_seconds": 1.0
  }
}
```

Execution is quarantined:

```text
RESULT = TASKS[plan["task"]](tracks, roi, plan["params"])
```

- Only known `task` values are allowed (validated by schema).  
- No arbitrary code execution.

---

## 6. Minimal Metric Modules (Restaurant Use-Case)

### Module 1: `dwell_count`

- **Definition:** A person “dwells” if their track’s center remains inside the ROI for ≥ `dwell_seconds`, allowing small jitter.  
- **Implementation:** ROI polygon → point-in-polygon; per track compute contiguous time inside ROI; emit dwell events.  

### Module 2: `traffic_count` (Optional but Easy)

- Count unique track IDs that enter the ROI at any point.  

These two cover most “storefront” questions for the MVP.

---

## 7. Data + Caching

Reruns should be fast. Cache artifacts keyed by:

- Video file hash  
- Model version  
- Detection params  
- Tracker params  
- Metric params  

**Suggested cached artifacts:**

- `detections.json`  
- `tracks.json`  
- `annotated_preview.mp4` (optional)  
- `results.json`  

Tweak a param → only re-run from the affected stage onward; reuse cached upstream outputs.

---

## 8. Incremental Build Order (Test After Every Step)

| Step | Deliverable | Test |
|------|-------------|------|
| **0** | Skeleton app: upload video, show first frame. Backend: read fps, frame count, resolution. | Video loads and renders. |
| **1** | ROI drawing on a frame (e.g. Streamlit drawable canvas or JS overlay). | ROI saved/reloaded; point-in-polygon works. |
| **2** | Person detection preview: run YOLO on a sample (e.g. 1 frame/sec). | Boxes on sample frames; confirm detection quality. |
| **3** | Full detection (all frames or every N). Cache to disk (key: video hash + model + params). | Progress bar; cached reruns are instant. |
| **4** | Tracking: detections → tracker → track IDs. Overlay tracks on video. | Track IDs stable across frames. |
| **5** | Dwell metric: `dwell_count(tracks, roi, params)`. Dwell events list + total count. | Click event → jump to timestamp; validate manually. |
| **6** | LLM planning: prompt → plan JSON. Validate with schema; run metric module. | Prompt variations map to same task reliably. |

---

## 9. Tooling

- **Project tracking:** GitHub Projects (kanban) or Linear  
- **Spec / checklist:** Notion or this doc  
- **Tests:** Pytest — e.g. point-in-polygon, dwell computation on synthetic tracks  
- **Code quality:** Pre-commit (black, ruff)  

---

## 10. What This MVP Is Not Doing (Intentionally)

- No code generation or execution from the model  
- No complex behavioral inference (pose, gaze, intent)  
- No promise of perfect accuracy — rely on visual evidence + event explorer for trust  

---

## 11. Possible Next Additions (Post-MVP)

- Repo structure (folders + module boundaries)  
- Exact JSON schema for the plan + validation rules  
- Minimal Streamlit UI layout (ROI drawing + step-by-step runs)  

This planning doc is the single source of truth for what is being built in the MVP.
