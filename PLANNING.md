# Videometric — Planning Document

This doc defines the MVP scope, tech stack, logic structure, and build order for **“Cursor for video analytics.”**

---

## 1. Product Definition & End Goal

**One sentence:** An AI-assisted workspace that lets users ask natural-language questions about video and iteratively build, inspect, and refine the logic used to answer them—backed by visual evidence and timestamped events.

**End goal:** The user types a question in plain English (e.g. *“How many people get on the bus?”*, *“What’s the average loitering time in front of this store?”*, *“How many people walk by wearing jeans?”*, *“Average number of people that cross the crosswalk at each red light?”*, *“How many times does the person in the green shirt raise their hand?”*). The app turns that into a **flexible, inspectable pipeline** that combines:

- **User-drawn ROI** — to restrict “where” (storefront, crosswalk, bus door, classroom region).
- **YOLO** — detection, tracking, and classification (person, vehicle, clothing/object classes as needed).
- **Optional body/pose tracking** — for actions like “raise hand” or “wave.”
- **Optional appearance/color logic** — e.g. “person in green shirt” via crop + color check or dedicated helpers.

The **LLM does not run code**. It produces a **structured JSON plan** that selects which **known functions and metric modules** run on the video. The result is the desired statistics plus **timestamped events** the user can click to jump to evidence in the video. Think: **flexible OpenCV-style pipelines, assembled from natural language and editable by the user.**

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

### C. When Is the Drawn ROI Used?

The **user-drawn ROI** is a spatial filter. It answers “where does the metric apply?” and is reused across many query types:

| User intent | How ROI is used |
|-------------|------------------|
| “Loitering time in front of this store” | User draws storefront zone. Dwell/loiter is computed only for tracks whose center stays inside this polygon. |
| “How many people cross the crosswalk?” | User draws the crosswalk. Count = unique tracks that enter (or cross) this zone; optionally gated by “per red light” if signal or time windows are available. |
| “How many people get on the bus?” | User draws bus door/entrance. Count entries into ROI (traffic_count or entry_count). |
| “Average number crossing at each red light” | Same crosswalk ROI; metric is “count per interval” where intervals come from signal or fixed time windows. |
| “Person in green shirt in this classroom raises hand” | User may draw classroom ROI to limit scope to one area; then tracking + color filter (“green shirt”) + pose (“hand raise”) run inside or relative to that region. |
| “Track all people who leave the ROI then come back” | User draws the zone (e.g. store, room). Metric uses ROI to compute per-track in/out over time and finds tracks that exited then re-entered. ROI defines the zone, not “which person.” |
| “Time this person spends on phone” / “Number of punches by this person” | ROI optional (e.g. to limit to one area). “Which person” = appearance filter (e.g. color). Pose/object logic runs on filtered tracks; no need to draw around the person. |

So: **ROI = user-defined zone**. It is not required for every query (e.g. “how many people in the whole frame”) but is essential for location-specific questions.

### D. Example Use Cases and How They’re Achieved

These are high-value cases to support; for each, the table states whether the user **draws an ROI** or the zone comes from **object detection (e.g. YOLO table)** and outlines the pipeline logic.

| Use case | ROI drawn? | How it’s achieved |
|----------|------------|--------------------|
| **Table turnover (avg seat time)** | **No.** | YOLO detects **person** and **dining table** (or generic “table”) in each frame. Vision outputs person tracks + table detections (or persistent table boxes). **Logic:** For each person track, associate to a table when the person’s bbox center (or feet) is inside a table’s bbox (or within a small margin). Per (track, table), compute contiguous time “at” that table = seat time. Aggregate: average seat time per table, or per-party (one track = one party). No user-drawn ROI; the “zone” is the detected table box. |
| **Window / display engagement** | **Yes.** | User draws an ROI **in front of** the window or display. **Logic:** `dwell_count` in that ROI: tracks whose center stays in the polygon for ≥ N seconds count as “engaged.” Report: count of people who lingered, and/or average dwell time. Optionally filter by direction (facing display) later with pose. |
| **Queue wait time** | **Yes.** | User draws an ROI for the queue (e.g. checkout line, drive-through). **Logic:** Same as dwell: time each track spends inside the queue ROI = wait time. Report: average wait time, max wait, or distribution. |
| **Foot traffic vs conversion (pass-by vs entered store)** | **Yes (one or two).** | Option A: One “store entrance” ROI. Count tracks that **enter** = conversions; optionally count tracks that **cross** a “pass-by” line (second ROI or line) but never enter = pass-by. Option B: Two ROIs — “sidewalk” (pass-by) and “inside store.” Tracks that enter store after being in sidewalk = conversion; traffic_count in each ROI gives pass-by vs inside. **Logic:** `traffic_count` per ROI; or a small “two_zone” metric: entered zone B after being in zone A. |
| **Occupancy (how many people in the store at peak?)** | **Yes.** | User draws one ROI = store floor (or room). **Logic:** Per time slice (e.g. every second or per minute), count how many track IDs have their center inside the ROI at that time. Report: max occupancy, or occupancy over time. Same primitive as “count in ROI per frame” / count_per_interval with short windows. |
| **Restricted zone intrusion** | **Yes.** | User draws ROI = no-go area. **Logic:** Any track that **enters** the ROI = one event (alert or count). Metric: `traffic_count` (entries) or a dedicated `intrusion_count` that only counts first entry per track. |
| **Leave ROI then come back** | **Yes.** | User draws an ROI (e.g. store entrance, room). **Logic:** For each track, compute in/out vs ROI per frame (point-in-polygon). Detect **exit** (in→out) and **re-entry** (out→in). Keep tracks that have at least one re-entry after an exit. Metric: `exit_reentry`. Report: list of such tracks + optional exit/re-entry timestamps; optional `min_time_outside_seconds` to ignore brief flickers. |
| **Time this person spends on their phone** | **Optional.** | No ROI required for the metric; optional ROI or appearance filter to restrict to “this person.” **Logic:** Vision detects **person** + **cell phone** (or pose: hand near face / “phone use” pose state). Associate phone to person (overlap or proximity); per track, sum time when phone is in hand or face region. Metric: `pose_state_dwell` (time in “phone_use” state) or `object_dwell` (time person bbox overlaps/near phone detection). Filter by appearance (e.g. “red shirt”) if “this person.” |
| **Number of punches thrown by this person** | **Optional.** | No ROI for the action; optional ROI (e.g. ring) or appearance filter to pick “this person.” **Logic:** Pose per frame; define “punch” as a fixed rule (e.g. arm extension + retraction, or fist forward). Metric: `pose_event_count` with `pose_event: "punch"`. Optionally filter tracks by `filters.appearance` (e.g. color) so only one person is counted. |

**Takeaway:** Use **drawn ROI** when the zone is arbitrary (storefront, window, queue, crosswalk, bus door). Use **object-derived zones** (e.g. YOLO “table”) when the zone is a detectable object — then associate person tracks to that object’s bbox and run dwell/count per zone. Supporting both keeps the pipeline flexible.

### E. Explicitly Out of MVP (For Now)

- Multi-camera  
- People attributes (age/gender) from a model — privacy and complexity  
- Cloud processing  
- Arbitrary code execution from the LLM  

---

## 3. Underlying Tech Stack

### Backend (Video + CV)

| Component | Choice | Role |
|-----------|--------|------|
| Language | Python | Glue + CV + API |
| Detection + Tracking | YOLOv8 / YOLOv11 (Ultralytics) | Person/object detection; **built-in tracking** (e.g. `.track()` with ByteTrack) — one API can yield both detections and track IDs across frames. |
| Pose (later) | Ultralytics pose model or same ecosystem | Body keypoints for “raise hand,” “wave,” etc. |
| Video I/O | OpenCV | Decode/encode, drawing overlays |
| Math | NumPy | Computations, point-in-polygon, color stats |

**Note on YOLO:** Using Ultralytics’ built-in tracking is recommended: run once per frame and get both boxes and stable track IDs. A separate “tracking stage” in the doc can still mean “the output of YOLO’s tracker” rather than a separate library, unless you later need a different tracker.

### Backend Folder Structure (Recommendation)

Keep **YOLO and vision logic in one place** so pipelines stay clear and testable:

- **`backend/app/core/`** — Decode (video → frames, fps, size). Stays model-agnostic.
- **`backend/app/vision/`** (or **`backend/app/yolo/`**) — All YOLO-related code: load model, run detect, run track (using Ultralytics’ tracker), optional pose, optional crop/color helpers. Input: frames + options; output: detections and/or tracks in a standard format.
- **`backend/app/metrics/`** — Metric modules: `dwell_count`, `traffic_count`, `count_per_interval`, `pose_event_count`, etc. Input: tracks (+ ROI, pose data, filters); output: events + aggregates.
- **`backend/app/pipeline/`** (optional) — Orchestration: take plan JSON, call decode → vision → metrics, return results. Can live in `main.py` or a small runner module instead.

This keeps “how we get boxes and tracks” (vision) separate from “what we compute from them” (metrics).

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

Stages are deterministic with clear input/output contracts so you can test after every step. **Detect and Track** can be a single vision step when using YOLO’s built-in tracker.

```
┌─────────────┐    ┌─────────────────────────┐    ┌─────────────┐
│   Decode    │ →  │   Vision (Detect+Track) │ →  │   Metric    │
│ video path  │    │   optional: pose, color │    │ tracks+ROI  │
│     ↓       │    │     ↓                   │    │     ↓       │
│ frames, fps │    │ tracks (id, box, cls,   │    │ events +    │
│ frame size  │    │ optional pose/keypoints)│    │ aggregates  │
└─────────────┘    └─────────────────────────┘    └─────────────┘
```

### Stage 1: Decode

- **Input:** Video path  
- **Output:** Frames iterator (or list), fps, frame size  

### Stage 2: Vision (Detect + Track, optional Pose / Appearance)

- **Input:** Frames; options (e.g. classes to detect, enable pose, sampling).  
- **Output:** Tracks over time, e.g.  
  `[{ track_id: 7, frame: 120, box: {...}, conf, cls: "person", optional: keypoints, crop_for_color }]`  
  Can be implemented by one YOLO pass (detect + built-in track) plus optional pose model or color extraction per track.

### Stage 3: Metric (Rules)

- **Input:** Tracks + ROI (if plan says so) + filters (e.g. “green shirt”) + parameters  
- **Output:**  
  - **Events:** e.g. “track 7 dwelled from t=12.3s to 18.1s”, “track 3 raised hand at t=45.2s”  
  - **Aggregates:** e.g. “total dwellers = 14”, “hand raises = 5”  

The LLM selects **which** metric module runs and **with what params**. The modules themselves are fixed and safe (no arbitrary code from the model).

---

## 5. Plan Format (AI → Safe Execution)

The LLM turns the user’s sentence into a **structured JSON plan**. Only known keys and task types are allowed (schema-validated); no arbitrary code execution.

**Example (dwell / loitering):**

```json
{
  "task": "dwell_count",
  "object": "person",
  "use_roi": true,
  "params": {
    "dwell_seconds": 5,
    "min_conf": 0.4,
    "min_track_seconds": 1.0
  }
}
```

**Example (count per interval, e.g. per red light):**

```json
{
  "task": "count_per_interval",
  "object": "person",
  "use_roi": true,
  "params": {
    "interval_source": "fixed_seconds",
    "interval_seconds": 90
  }
}
```

**Example (pose-based: hand raises for a filtered person):**

```json
{
  "task": "pose_event_count",
  "object": "person",
  "use_roi": true,
  "filters": {
    "appearance": { "color_region": "torso", "hue_range": "green" }
  },
  "params": {
    "pose_event": "hand_raise",
    "min_confidence": 0.5
  }
}
```

**Example (tracks that leave the ROI then come back):**

```json
{
  "task": "exit_reentry",
  "object": "person",
  "use_roi": true,
  "params": {
    "min_time_outside_seconds": 0.5
  }
}
```

**Example (pose-only: count punches by a filtered person, no ROI):**

```json
{
  "task": "pose_event_count",
  "object": "person",
  "use_roi": false,
  "filters": {
    "appearance": { "color_region": "torso", "hue_range": "red" }
  },
  "params": {
    "pose_event": "punch",
    "min_confidence": 0.5
  }
}
```

**Example (time this person spends on phone — pose state dwell):**

```json
{
  "task": "pose_state_dwell",
  "object": "person",
  "use_roi": false,
  "filters": {
    "appearance": { "color_region": "torso", "hue_range": "blue" }
  },
  "params": {
    "pose_state": "phone_use",
    "min_confidence": 0.4
  }
}
```

Execution stays quarantined:

```text
tracks = run_vision(frames, plan)
if plan.get("use_roi"): apply_roi_filter(tracks, user_roi_polygon)
if plan.get("filters"): apply_filters(tracks, plan["filters"])
RESULT = TASKS[plan["task"]](tracks, roi_if_used, plan["params"])
```

- Only known `task` values and filter keys are allowed.  
- ROI comes from the user-drawn polygon stored for the current video (referenced when `use_roi` is true).

---

## 6. Metric Modules (Known Functions the LLM Can Invoke)

Each metric is a **fixed, safe function** with a clear signature. The LLM picks the task and params; it does not write code.

| Task | Description | Typical queries |
|------|-------------|------------------|
| **dwell_count** | Tracks whose center stays in ROI ≥ `dwell_seconds` (with jitter tolerance). Emit dwell events + total count, average loiter time. | “Average loitering time in front of this store” |
| **traffic_count** | Unique track IDs that enter (or cross) the ROI. | “How many people get on the bus?”, “How many cross the crosswalk?” |
| **count_per_interval** | Same as traffic or count, but segmented by time windows (e.g. per red light cycle or fixed N seconds). | “Average number that cross at each red light” |
| **exit_reentry** | Tracks that **leave** the ROI and later **re-enter** it. Per-track in/out over time; detect exit (in→out) and re-entry (out→in); list or count tracks with ≥1 re-entry after an exit. Optional `min_time_outside_seconds` to ignore flicker. | “Track all people who leave the ROI then come back” |
| **pose_event_count** | Count discrete pose events (e.g. hand raise, wave, punch) per track, optionally filtered by appearance. Event definitions (e.g. “punch” = arm extension) are **fixed in backend code**; LLM only selects event name. | “How many times does the person in the green shirt raise their hand?”, “Number of punches thrown by this person” |
| **pose_state_dwell** | Total time per track that a pose/object state holds (e.g. “phone in use”). Sum frames where state is true; report seconds per track. Can use pose (hand at face) or object co-occurrence (phone near person). | “Track the time this person spends on their phone” |
| **attribute_count** (later) | Filter tracks by appearance (e.g. color in a region, “jeans” if a classifier is available), then count or dwell. | “How many people walk by wearing jeans?” |

**Implementation notes:**

- **dwell_count:** ROI polygon → point-in-polygon; per track compute contiguous time inside ROI; emit events + aggregates.  
- **traffic_count:** Point-in-polygon for entry/exit or crossing; count unique track IDs.  
- **count_per_interval:** Same as above but bucket by time windows (from params or future signal input).  
- **exit_reentry:** Per track, in/out vs ROI per frame; scan for exit then re-entry transitions; emit list of track IDs (and optional timestamps) that left then came back.  
- **pose_event_count:** Requires pose/keypoints in tracks; predefined rules per event (e.g. hand_raise = wrist above shoulder, punch = arm extension); optionally filter tracks by `filters.appearance` first.  
- **pose_state_dwell:** Pose or object detection per frame; “phone_use” = hand near face or phone bbox near person; sum duration per track; optionally filter by appearance for “this person.”  
- **attribute_count:** Use crops or ROIs on each track; run color histograms or a small classifier; then apply count or dwell logic on filtered tracks.

Adding a new metric = add a new module + register it in the plan schema so the LLM can select it.

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

**Why this order:** Each step delivers a testable outcome and gets you closer to “ask in NL → get metrics + timestamps.” Early steps give you the pipeline (decode, vision, ROI); later steps add metrics and then let the LLM choose which metric and params.

| Step | Deliverable | Test |
|------|-------------|------|
| **0** | Skeleton app: upload video, show first frame. Backend: read fps, frame count, resolution. | Video loads and renders. |
| **1** | ROI drawing on a frame; save/reload via API; overlay on video. Optional: point-in-polygon helper (for metrics). | ROI saved/reloaded; overlay correct. |
| **2** | **Vision folder + person detection preview:** Run YOLO on a sample (e.g. 1 frame/sec). Return boxes (and optionally use built-in track for IDs). | Boxes on sample frames; confirm detection quality. |
| **3** | Full vision run (all frames or every N). Use YOLO’s `.track()` so output is **tracks** (id + box per frame). Cache to disk (video hash + model + params). | Progress bar; cached reruns instant; track IDs stable. |
| **4** | **Metric: dwell_count.** `dwell_count(tracks, roi, params)`. Dwell events list + total count + average duration. Event explorer: click → jump to timestamp. | Click event → jump; validate manually. |
| **5** | **Metric: traffic_count.** Unique tracks entering ROI. Optional: count_per_interval (e.g. per N seconds). | Counts match intuition; intervals work. |
| **6** | **LLM planning:** Prompt → plan JSON. Validate with schema; map to task + params; run pipeline (vision → ROI filter → metric). | Prompt variations map to same task reliably. |
| **7** | (Later) **Pose:** Add pose to vision output; metric `pose_event_count` (e.g. hand raise). | Pose events detected; count correct. |
| **8** | (Later) **Appearance filters:** Color (e.g. green shirt) or simple attribute; use in filters before metric. | “Person in green shirt” filters tracks; metric runs on filtered set. |

**End goal after build:** User asks “How many people get on the bus?” → LLM outputs a plan with `traffic_count` + `use_roi: true` → user has drawn bus-door ROI → pipeline runs → results + timestamped events; user can tweak params and re-run. Same flow for loitering, crosswalk per red light, hand raises with optional color filter, etc.

---

## 9. Tooling

- **Project tracking:** GitHub Projects (kanban) or Linear  
- **Spec / checklist:** Notion or this doc  
- **Tests:** Pytest — e.g. point-in-polygon, dwell computation on synthetic tracks  
- **Code quality:** Pre-commit (black, ruff)  

---

## 10. What This MVP Is Not Doing (Intentionally)

- **No code generation or execution from the model** — only schema-validated plan JSON that triggers known modules.  
- **No promise of perfect accuracy** — rely on visual evidence (boxes, tracks, annotated video) and event explorer (click → timestamp) for trust.  
- Pose and appearance (color, “jeans”) are **post–first-MVP** extensions: the pipeline is designed so they can be added as optional vision outputs and filters without changing the core flow.

---

## 11. Possible Next Additions (Post-MVP)

- Exact JSON schema for the plan + validation rules (e.g. Pydantic).  
- Step-by-step run mode in the UI: run “vision only” → “metric only” for debugging.  
- Red-light / signal detection or manual time windows for “per red light” metrics.  
- Stronger attribute models (e.g. clothing) if “wearing jeans” is required.  

---

## 12. Open Questions (To Decide as You Build)

- **Red light / crosswalk intervals:** For “average number crossing at each red light,” do you have signal data (e.g. another video or API), or should the app use fixed time windows / manual segment markers for now?  
- **Color/appearance:** Prefer simple color histograms on track crops (fast, good for “green shirt”) or a small classifier?  
- **Pose:** Use Ultralytics pose model (same ecosystem as YOLO) or a separate library (e.g. MediaPipe) for “hand raise” and similar events?  
- **LLM:** Which model and where it runs (e.g. OpenAI, local) — affects latency and cost for “prompt → plan.”  

---

This planning doc is the single source of truth for the product and pipeline. Adjust as you lock in tech choices (e.g. YOLO folder name, exact plan schema).
