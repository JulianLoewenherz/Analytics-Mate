# Pipeline Logic — From Natural Language to Video Metrics

**Scope:** This doc covers everything after ROI drawing: how a natural-language prompt becomes a structured JSON plan, what libraries run the vision, and how the JSON plan is executed as a real pipeline.

**Design principle:** Build a small set of composable primitives. The LLM's job is to pick which primitives to compose and with what parameters. Every new use case is either (a) a new combination of existing primitives or (b) one new primitive added to the registry. The system grows by adding modules, never by generating arbitrary code.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The Analysis Plan JSON — Full Schema](#2-the-analysis-plan-json--full-schema)
3. [Schema Reference — Every Field Explained](#3-schema-reference--every-field-explained)
4. [Concrete JSON Examples for Every Use Case](#4-concrete-json-examples-for-every-use-case)
5. [NL → JSON: How the LLM Produces a Plan](#5-nl--json-how-the-llm-produces-a-plan)
   - [When the Plan Requires an ROI but None Exists](#56--when-the-plan-requires-an-roi-but-none-exists)
6. [Vision Stack — What Libraries and Models to Use](#6-vision-stack--what-libraries-and-models-to-use)
7. [Pipeline Execution — How JSON Becomes a Running Script](#7-pipeline-execution--how-json-becomes-a-running-script)
8. [Metric Modules — The Primitives](#8-metric-modules--the-primitives)
9. [Filter System — Appearance, Object Co-occurrence, Pose](#9-filter-system--appearance-object-co-occurrence-pose)
10. [Output Contract — What Every Pipeline Returns](#10-output-contract--what-every-pipeline-returns)
11. [Caching Strategy](#11-caching-strategy)
12. [Implementation Order — One Section at a Time](#12-implementation-order--one-section-at-a-time)
13. [Extending the System — Adding New Capabilities](#13-extending-the-system--adding-new-capabilities)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER PROMPT                              │
│  "How many people loiter in front of my store for > 10 sec?"    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LLM PLANNER                                 │
│  System prompt + schema + user ROI context                      │
│  → Produces validated JSON plan                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PLAN VALIDATOR (Pydantic)                       │
│  Checks plan against schema; rejects unknown tasks/fields       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   PIPELINE RUNNER                                │
│                                                                 │
│  Step 1: DECODE ─── video → frames + fps + dimensions           │
│              │                                                   │
│  Step 2: VISION ─── frames → raw detections + tracks            │
│              │       (YOLO detect+track, optional pose)          │
│              │                                                   │
│  Step 3: FILTER ─── tracks → filtered tracks                    │
│              │       (ROI filter, appearance, object assoc.)     │
│              │                                                   │
│  Step 4: METRIC ─── filtered tracks → events + aggregates       │
│              │       (dwell, traffic, count_per_interval, etc.)  │
│              │                                                   │
│  Step 5: FORMAT ─── events + aggregates → JSON result + overlay │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RESULTS + EVIDENCE                            │
│  { aggregates, events[], annotated_frames }                     │
│  → UI renders metrics, event timeline, annotated video          │
└─────────────────────────────────────────────────────────────────┘
```

Key insight: Steps 1-2 (Decode + Vision) are **shared infrastructure**. The same YOLO tracking output feeds every metric. Steps 3-4 (Filter + Metric) are **plan-specific** — the JSON plan determines which filters and which metric module run.

---

## 2. The Analysis Plan JSON — Full Schema

This is the **complete schema** that the LLM is allowed to produce. Every field is either required or optional with a default. Unknown fields are rejected.

```json
{
  "task": "string (required)",
  "object": "string (required)",
  "use_roi": "boolean (required)",

  "vision": {
    "model": "string (default: 'yolo26n')",
    "enable_tracking": "boolean (default: true)",
    "enable_pose": "boolean (default: false)",
    "detect_classes": ["string"],
    "sample_fps": "number | null (default: null = process every frame)",
    "confidence_threshold": "number (default: 0.4)"
  },

  "filters": {
    "roi_mode": "string: 'inside' | 'enters' | 'crosses' | 'outside' (default: 'inside')",
    "appearance": {
      "color_region": "string: 'torso' | 'full' | 'lower' | 'upper'",
      "color": "string (e.g. 'green', 'red', 'blue')"
    },
    "object_association": {
      "associate_with": "string (e.g. 'dining table', 'cell phone')",
      "method": "string: 'bbox_overlap' | 'proximity' | 'containment'",
      "max_distance_px": "number (optional)"
    },
    "min_track_frames": "number (default: 5)",
    "min_confidence": "number (default: 0.4)"
  },

  "params": {
    "...task-specific parameters..."
  },

  "output": {
    "include_events": "boolean (default: true)",
    "include_aggregates": "boolean (default: true)",
    "include_annotated_frames": "boolean (default: false)",
    "include_timeline": "boolean (default: true)"
  },

  "roi_instruction": "string (optional, for UI)"
}
```

### Why this shape?

- **`task`** picks the metric module. One task = one well-defined computation.
- **`object`** specifies the primary entity the metric measures (e.g. person dwell time, car count). This is what you're counting or computing metrics about.
- **`vision.detect_classes`** specifies which YOLO classes to actually detect. Can be a superset of `object` when you need secondary objects for context (e.g. detect both "person" and "dining table" to compute person-at-table metrics).
  - **Single-class queries:** `object` and `detect_classes` match (e.g. `object: "car"`, `detect_classes: ["car"]`)
  - **Multi-class queries:** `detect_classes` includes additional objects needed for association (e.g. `object: "person"`, `detect_classes: ["person", "cell phone"]` to compute phone-use time)
- **`use_roi`** determines if the saved user-drawn polygon is loaded and applied.
- **`vision`** configures the YOLO pass (model size, pose, which classes, sampling rate).
- **`filters`** is the "narrowing" layer — spatial (ROI), appearance (color), object co-occurrence (phone near person, person at table), and track quality (min frames, confidence).
- **`params`** holds task-specific knobs (dwell threshold, interval length, pose event name, etc.).
- **`output`** controls what the result contains (events, aggregates, annotated frames).
- **`roi_instruction`** (optional) is a short, human-readable hint for *where* to draw the ROI when the plan requires one but none exists yet (e.g. "Draw an ROI on the crosswalk", "Draw around the bus door"). The LLM can derive this from the user prompt; the frontend shows it when prompting the user to draw.

---

## 3. Schema Reference — Every Field Explained

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task` | string | Yes | Which metric module to run. Must be a registered task name (see Section 8). |
| `object` | string | Yes | Primary entity the metric measures. Maps to YOLO class (e.g. `"person"`, `"car"`, `"bicycle"`). For multi-class queries, this is the main subject while `vision.detect_classes` may include additional classes. |
| `use_roi` | boolean | Yes | Whether to use the user-drawn ROI polygon as a spatial filter. |
| `roi_instruction` | string | No | Short hint for the user on *where* to draw the ROI when none exists (e.g. "Draw an ROI on the crosswalk"). Used by the UI when returning `needs_roi`. |

### `vision` Block

Controls how YOLO processes the video. Defaults are sensible for most queries.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | `"yolo26n"` | YOLO model variant. Options: `yolo26n` (fast), `yolo26s` (balanced), `yolo26m` (accurate). YOLO26 is smaller/faster than YOLO11; nano is fine for MVP. |
| `enable_tracking` | bool | `true` | Use YOLO's built-in ByteTrack to assign persistent track IDs across frames. Almost always true. |
| `enable_pose` | bool | `false` | Run YOLO-Pose to get 17 body keypoints per person. Only needed for pose-based tasks. |
| `detect_classes` | string[] | `["person"]` | YOLO class names to detect. Can include multiple (e.g. `["person", "cell phone"]` for phone-use detection). |
| `sample_fps` | number\|null | `null` | If set, process only N frames per second instead of every frame. Useful for long videos. `null` = every frame. |
| `confidence_threshold` | number | `0.4` | Minimum detection confidence to keep a box. |

### `filters` Block

Narrows tracks after vision, before the metric module runs.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `roi_mode` | string | `"inside"` | How ROI is applied: `"inside"` (center point in polygon), `"enters"` (track transitions from outside to inside), `"crosses"` (track intersects polygon boundary), `"outside"` (center point outside polygon). |
| `appearance` | object\|null | `null` | Color-based filter on track crops. |
| `appearance.color_region` | string | `"torso"` | Which part of the person bbox to sample color from. |
| `appearance.color` | string | — | Target color name (mapped to HSV range internally). |
| `object_association` | object\|null | `null` | Associate primary object tracks with another detected object type. |
| `object_association.associate_with` | string | — | YOLO class name of the secondary object (e.g. `"dining table"`, `"cell phone"`). |
| `object_association.method` | string | `"bbox_overlap"` | How to associate: bbox IoU overlap, proximity (center distance), or containment (one inside another). |
| `object_association.max_distance_px` | number | `50` | Max pixel distance for `"proximity"` method. |
| `min_track_frames` | number | `5` | Discard tracks shorter than this (reduces noise). |
| `min_confidence` | number | `0.4` | Discard detections below this confidence. |

### `params` Block — Per Task

Each task defines its own params. See Section 8 for every task's param spec.

### `output` Block

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `include_events` | bool | `true` | Return list of timestamped events. |
| `include_aggregates` | bool | `true` | Return summary stats (counts, averages, etc.). |
| `include_annotated_frames` | bool | `false` | Generate annotated frame images with bboxes + track IDs. |
| `include_timeline` | bool | `true` | Return per-frame or per-second occupancy/count data for timeline charts. |

---

## 4. Concrete JSON Examples for Every Use Case

### 4.1 — "How many people loiter in front of my store for more than 10 seconds?"

```json
{
  "task": "dwell_count",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "enable_pose": false,
    "detect_classes": ["person"],
    "confidence_threshold": 0.4
  },
  "filters": {
    "roi_mode": "inside",
    "min_track_frames": 5
  },
  "params": {
    "dwell_threshold_seconds": 10,
    "jitter_tolerance_px": 15
  },
  "output": {
    "include_events": true,
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

**Pipeline:** Decode → YOLO track persons → filter tracks to ROI (center inside polygon) → for each track, compute contiguous time inside ROI → emit dwell events where time >= 10s → aggregate (count, avg duration).

---

### 4.2 — "How much time do people spend on their phone?" (Multi-class detection)

```json
{
  "task": "object_co_occurrence_dwell",
  "object": "person",
  "use_roi": false,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person", "cell phone"]
  },
  "filters": {
    "object_association": {
      "associate_with": "cell phone",
      "method": "proximity",
      "max_distance_px": 100
    },
    "min_track_frames": 10
  },
  "params": {
    "association_threshold_seconds": 0.5
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

**Pipeline:** Decode → YOLO detects both persons (tracked) and cell phones (detections) → for each person track, find frames where a cell phone detection is within 100px → compute contiguous time with phone association → emit per-person phone usage duration.

**Note:** This demonstrates multi-class detection where `object: "person"` (what we measure) but `detect_classes: ["person", "cell phone"]` (what YOLO must see to compute the association).

---

### 4.3 — "How many people cross the crosswalk?"

```json
{
  "task": "traffic_count",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "crosses",
    "min_track_frames": 5
  },
  "params": {
    "count_mode": "unique_crossings"
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

---

### 4.4 — "Average number of people crossing at each red light" (per-interval count)

```json
{
  "task": "count_per_interval",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "crosses"
  },
  "params": {
    "interval_source": "fixed_seconds",
    "interval_seconds": 90,
    "aggregation": "average"
  },
  "output": {
    "include_events": true,
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

**Pipeline:** Same as traffic_count, but bucket crossing events into time windows (every 90s as proxy for light cycle). Compute count per window, then average across windows.

---

### 4.5 — "Person in green shirt raises their hand in this classroom"

```json
{
  "task": "pose_event_count",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n-pose",
    "enable_tracking": true,
    "enable_pose": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "inside",
    "appearance": {
      "color_region": "torso",
      "color": "green"
    }
  },
  "params": {
    "pose_event": "hand_raise",
    "min_hold_frames": 3
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

**Pipeline:** Decode → YOLO-Pose track persons (get keypoints) → filter to ROI → filter by torso color (green) → for remaining tracks, detect frames where wrist keypoint is above shoulder keypoint → count hand-raise events.

---

### 4.6 — "Track all people who leave the ROI then come back"

```json
{
  "task": "exit_reentry",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "inside"
  },
  "params": {
    "min_time_outside_seconds": 2.0
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

**Pipeline:** Decode → YOLO track → per track, compute in/out status vs ROI per frame → find tracks that transition in→out→in → filter out flicker (must be outside >= 2s) → emit exit/reentry events.

---

### 4.7 — "Table turnover / average seat time" (object-derived zones, no drawn ROI)

```json
{
  "task": "dwell_count",
  "object": "person",
  "use_roi": false,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person", "dining table"]
  },
  "filters": {
    "object_association": {
      "associate_with": "dining table",
      "method": "containment",
      "max_distance_px": 30
    },
    "min_track_frames": 30
  },
  "params": {
    "dwell_threshold_seconds": 0,
    "group_by": "associated_object"
  },
  "output": {
    "include_events": true,
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

**Pipeline:** Decode → YOLO detect+track persons AND tables → for each person track, check if center is inside any table bbox (or within 30px) → assign person→table association → per (person, table), compute time "at" the table = seat time → aggregate per table (avg seat time, turnover count).

---

### 4.8 — "Window/display engagement — who stops and looks?"

```json
{
  "task": "dwell_count",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "inside",
    "min_track_frames": 10
  },
  "params": {
    "dwell_threshold_seconds": 3
  },
  "output": {
    "include_events": true,
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

---

### 4.9 — "Queue wait time"

```json
{
  "task": "dwell_count",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "inside"
  },
  "params": {
    "dwell_threshold_seconds": 0,
    "report_per_track": true
  },
  "output": {
    "include_events": true,
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

**Pipeline:** Same as dwell_count but with 0s threshold (report all dwell times). Aggregates: average wait time, max wait, distribution.

---

### 4.10 — "Occupancy over time (how many people in the store at peak?)"

```json
{
  "task": "occupancy",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "inside"
  },
  "params": {
    "time_resolution_seconds": 1
  },
  "output": {
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

**Pipeline:** Decode → YOLO track → per time slice (every 1s), count distinct track IDs with center inside ROI → produce time series + peak occupancy.

---

### 4.11 — "Restricted zone intrusion"

```json
{
  "task": "traffic_count",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "enters"
  },
  "params": {
    "count_mode": "first_entry_only"
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

---

### 4.12 — "Time this person (in blue shirt) spends on their phone"

```json
{
  "task": "object_co_occurrence_dwell",
  "object": "person",
  "use_roi": false,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person", "cell phone"]
  },
  "filters": {
    "appearance": {
      "color_region": "torso",
      "color": "blue"
    },
    "object_association": {
      "associate_with": "cell phone",
      "method": "proximity",
      "max_distance_px": 80
    }
  },
  "params": {
    "report_per_track": true
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

**Pipeline:** Decode → YOLO track persons + cell phones → filter persons by torso color (blue) → for each remaining person track, check per frame if a cell phone detection is within 80px → sum time when phone is associated → report total seconds on phone.

---

### 4.13 — "Number of punches thrown by person in red"

```json
{
  "task": "pose_event_count",
  "object": "person",
  "use_roi": false,
  "vision": {
    "model": "yolo26n-pose",
    "enable_tracking": true,
    "enable_pose": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "appearance": {
      "color_region": "torso",
      "color": "red"
    }
  },
  "params": {
    "pose_event": "punch",
    "min_hold_frames": 2
  },
  "output": {
    "include_events": true,
    "include_aggregates": true
  }
}
```

---

### 4.14 — "Foot traffic vs conversion (pass-by vs entered store)"

```json
{
  "task": "multi_zone_comparison",
  "object": "person",
  "use_roi": true,
  "vision": {
    "model": "yolo26n",
    "enable_tracking": true,
    "detect_classes": ["person"]
  },
  "filters": {
    "roi_mode": "enters"
  },
  "params": {
    "compare": "pass_by_vs_enter",
    "entry_zone": "roi_primary"
  },
  "output": {
    "include_events": true,
    "include_aggregates": true,
    "include_timeline": true
  }
}
```

**Note:** This is a later-stage task. For MVP, the user can approximate by running `traffic_count` on a store-entrance ROI (entries = conversions) and separately on a sidewalk ROI (entries = foot traffic).

---

## 5. NL → JSON: How the LLM Produces a Plan

### 5.1 — The Planner Endpoint

```
POST /api/video/{video_id}/plan
Body: { "prompt": "How many people loiter for > 10s?" }
Response: { "plan": { ...validated JSON... }, "explanation": "..." }
```

### 5.2 — The LLM System Prompt (Conceptual)

The LLM receives a system prompt that contains:

1. **The full plan schema** — every allowed field, type, and enum value.
2. **The list of registered tasks** — with one-line descriptions and param specs.
3. **Context about this video** — whether an ROI exists, video duration, fps.
4. **Few-shot examples** — 5-6 prompt→plan pairs covering the major task types.
5. **Strict rules:**
   - Only produce JSON matching the schema.
   - Only use registered task names.
   - If the prompt is ambiguous, pick the most likely task and explain the choice in `explanation`.
   - If the prompt requires capabilities not yet supported, say so in `explanation` and produce the closest available plan.

### 5.3 — System Prompt Template

```
You are the planning engine for a video analytics application.

Given a user's natural-language question about a video, produce a JSON analysis plan
that selects the correct metric module, vision configuration, filters, and parameters.

## Available Tasks
{TASK_REGISTRY_DOCS}

## Plan Schema
{JSON_SCHEMA}

## Context for This Video
- ROI exists: {roi_exists}
- ROI name: {roi_name}
- Video duration: {duration_seconds}s
- Video resolution: {width}x{height}

## Rules
1. Output ONLY valid JSON matching the schema. No extra fields.
2. task must be one of: {list_of_task_names}
3. If the user mentions a zone/area/region and ROI exists, set use_roi: true.
4. If the user mentions a specific person by appearance (color, clothing), add filters.appearance.
5. If the query requires pose (hand raise, punch, wave), set vision.enable_pose: true
   and use the pose model variant.
6. If the query involves an object interaction (phone, table), add the secondary class
   to vision.detect_classes and configure filters.object_association.
7. Provide an "explanation" field (string) summarizing your reasoning.

## Examples
{FEW_SHOT_EXAMPLES}

User prompt: "{user_prompt}"
```

### 5.4 — Which LLM to Use

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **OpenAI GPT-4o-mini** | Fast, cheap ($0.15/1M input), good at structured JSON, supports `response_format: json_object` | Requires API key, external call | **Best for MVP.** Fast, reliable JSON, cheap. |
| **OpenAI GPT-4o** | Most capable for ambiguous prompts | More expensive ($2.50/1M input) | Use as fallback if mini fails. |
| **Claude 3.5 Haiku** | Fast, good at following schemas | Different API | Alternative to GPT-4o-mini. |
| **Local (Ollama + Llama 3)** | Free, private, no API key | Slower, less reliable JSON output | Later option for offline mode. |

**MVP recommendation:** Use **GPT-4o-mini** with `response_format: { type: "json_object" }`. It's fast (~300ms), cheap, and reliably produces schema-valid JSON. Add Pydantic validation as a safety net.

### 5.5 — Validation with Pydantic

After the LLM returns JSON, validate it with a Pydantic model before execution:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from enum import Enum

class TaskName(str, Enum):
    dwell_count = "dwell_count"
    traffic_count = "traffic_count"
    count_per_interval = "count_per_interval"
    occupancy = "occupancy"
    exit_reentry = "exit_reentry"
    pose_event_count = "pose_event_count"
    object_co_occurrence_dwell = "object_co_occurrence_dwell"
    # Add more as implemented

class AppearanceFilter(BaseModel):
    color_region: Literal["torso", "full", "lower", "upper"] = "torso"
    color: str  # mapped to HSV range internally

class ObjectAssociation(BaseModel):
    associate_with: str  # YOLO class name
    method: Literal["bbox_overlap", "proximity", "containment"] = "bbox_overlap"
    max_distance_px: Optional[int] = 50

class VisionConfig(BaseModel):
    model: str = "yolo26n"
    enable_tracking: bool = True
    enable_pose: bool = False
    detect_classes: list[str] = ["person"]
    sample_fps: Optional[float] = None
    confidence_threshold: float = 0.4

class Filters(BaseModel):
    roi_mode: Literal["inside", "enters", "crosses", "outside"] = "inside"
    appearance: Optional[AppearanceFilter] = None
    object_association: Optional[ObjectAssociation] = None
    min_track_frames: int = 5
    min_confidence: float = 0.4

class OutputConfig(BaseModel):
    include_events: bool = True
    include_aggregates: bool = True
    include_annotated_frames: bool = False
    include_timeline: bool = True

class AnalysisPlan(BaseModel):
    task: TaskName
    object: str
    use_roi: bool
    vision: VisionConfig = VisionConfig()
    filters: Filters = Filters()
    params: dict  # Task-specific; validated per-task
    output: OutputConfig = OutputConfig()
    explanation: Optional[str] = None
    roi_instruction: Optional[str] = None  # e.g. "Draw an ROI on the crosswalk"

    @validator("params")
    def validate_params_for_task(cls, v, values):
        # Per-task param validation happens here
        # (See Section 8 for each task's required params)
        return v
```

If validation fails, the backend returns the error to the frontend so the user can see what went wrong and adjust their prompt or the plan directly.

---

### 5.6 — When the Plan Requires an ROI but None Exists

If the plan has `use_roi: true` and the backend has no saved ROI for that video, the pipeline should **not** run. Instead, the API should return a response that tells the frontend to prompt the user to draw an ROI, with optional contextual text.

**API contract:**

- **Request:** `POST /api/video/{video_id}/analyze` with `{ "prompt": "..." }` or `{ "plan": { ... } }`.
- **Backend logic:** After generating/validating the plan, if `plan.use_roi is True` and `GET /api/video/{video_id}/roi` returns 404 (or empty):
  - Return **HTTP 200** with a structured body that indicates "needs ROI", so the client can show UI instead of an error:
    ```json
    {
      "status": "needs_roi",
      "plan": { ... validated plan ... },
      "roi_instruction": "Draw an ROI on the crosswalk so we can count people who cross it.",
      "message": "This analysis needs a region of interest. Draw one on the video, then run again."
    }
    ```
  - Do **not** run the pipeline.
- **`roi_instruction`** should come from the plan when the LLM provides it (e.g. derived from the user prompt: "cross the crosswalk" → "Draw an ROI on the crosswalk"). If the plan has no `roi_instruction`, the backend can use a generic fallback, e.g. *"Draw a region of interest around the area you want to analyze (e.g. crosswalk, store entrance, or queue)."*

**LLM instruction for the planner:** When `use_roi` is true, the LLM should also output a short `roi_instruction` string (1–2 sentences) telling the user *where* to draw, e.g.:
- "How many people cross the crosswalk?" → `"Draw an ROI on the crosswalk."`
- "How many people get on the bus?" → `"Draw an ROI around the bus door or entrance."`
- "Loitering time in front of my store" → `"Draw an ROI in front of the storefront."`

**Frontend behavior:**

1. When the user clicks Run and the response has `status === "needs_roi"`:
   - Show the **plan** (so they see what will run).
   - Show a clear message: e.g. *"This analysis needs a region of interest."*
   - Display **`roi_instruction`** prominently (e.g. in the evidence pane or a toast/banner): *"Draw an ROI on the crosswalk so we can count people who cross it."*
   - Provide a clear CTA: **"Draw ROI"** that takes them to the ROI drawing flow (e.g. focus evidence pane, open Draw ROI mode).
2. After the user saves an ROI, they can click Run again; this time the backend will have an ROI and will execute the pipeline.

**Optional: instructions on *how* to draw**

For first-time users, the app can show brief instructions when entering ROI-draw mode, e.g.:
- *"Click on the video to add points. Double-click or click near the first point to close the polygon. Draw around the area you want to measure (e.g. crosswalk, entrance)."*
- This can live in the evidence pane (collapsible tip) or in the ROI canvas modal. It does not need to be in the plan JSON; it's static UX copy.

---

## 6. Vision Stack — What Libraries and Models to Use

### 6.1 — Core: Ultralytics YOLO (one library for detection, tracking, and pose)

**Library:** `ultralytics` (pip install ultralytics)

**Recommended for new projects: YOLO26** (released 2025–2026). YOLO26 is smaller, faster, and easier to deploy than YOLO11, with better CPU inference and the same detection/tracking/pose API. Use YOLO26 unless you have a reason to stay on YOLO11.

**Why Ultralytics YOLO for everything:**
- **Detection:** YOLO detects 80 COCO classes (person, car, bicycle, cell phone, dining table, etc.) out of the box.
- **Tracking:** Built-in `.track()` method uses ByteTrack. One call gives you bounding boxes + persistent track IDs across frames. No separate tracker library needed.
- **Pose:** YOLO26-Pose (or YOLO11-Pose) gives 17 COCO keypoints per detected person. Same API, different model file.
- **Single ecosystem:** Same API for detect, track, and pose. Minimal integration friction.

| Need | Model | File | What It Returns |
|------|-------|------|-----------------|
| Detection + Tracking | YOLO26 nano | `yolo26n.pt` | boxes, class IDs, confidences, track IDs |
| Detection + Tracking (higher accuracy) | YOLO26 small | `yolo26s.pt` | Same, ~2x slower but better accuracy |
| Pose + Tracking | YOLO26-Pose nano | `yolo26n-pose.pt` | boxes, track IDs, + 17 keypoints per person |
| Pose + Tracking (higher accuracy) | YOLO26-Pose small | `yolo26s-pose.pt` | Same, higher accuracy |

*If YOLO26 is not yet available in your `ultralytics` version, use `yolo11n` / `yolo11n-pose.pt` as fallback; the pipeline code is the same.*

### 6.2 — Supporting Libraries

| Library | Purpose | When Used |
|---------|---------|-----------|
| `opencv-python` | Video decode/encode, frame manipulation, color conversion | Always (already installed) |
| `numpy` | Point-in-polygon, color histograms, array math | Always (already installed) |
| `shapely` | Robust polygon operations (point-in-polygon, intersection, area) | ROI filtering — more reliable than manual numpy PIP |
| `scikit-learn` (optional) | KMeans for dominant color extraction from track crops | Appearance filtering |

### 6.3 — What We Are NOT Using (and Why)

| Library | Why Not |
|---------|---------|
| **DeepSORT / StrongSORT** | YOLO's built-in ByteTrack is good enough for MVP. These add re-ID (re-identification after occlusion) which is nice but adds complexity. Can swap in later if ByteTrack's ID switches cause problems. |
| **MediaPipe Pose** | Ultralytics pose keeps everything in one ecosystem. MediaPipe is better for single-person close-up but YOLO-Pose handles multi-person scenes better. |
| **Detectron2** | Heavier, more complex API, no built-in tracking. YOLO is simpler and faster for our use cases. |
| **MMDetection / MMPose** | Same reasoning — more powerful but more complex. YOLO is the right tradeoff for MVP. |

### 6.4 — Vision Module Code Structure

```
backend/app/vision/
├── __init__.py
├── detector.py        # Wraps YOLO detect + track
├── pose.py            # Wraps YOLO-Pose
├── color.py           # Color extraction from track crops
├── association.py     # Object-to-object association (person↔table, person↔phone)
└── models.py          # Pydantic models for Track, Detection, Keypoints, etc.
```

### 6.5 — The Track Data Structure (Core Abstraction)

Everything downstream (filters, metrics) works on **Track** objects. This is the critical data contract:

```python
from pydantic import BaseModel
from typing import Optional

class BBox(BaseModel):
    x1: float  # top-left x
    y1: float  # top-left y
    x2: float  # bottom-right x
    y2: float  # bottom-right y

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

class Keypoints(BaseModel):
    """17 COCO keypoints, each (x, y, confidence)"""
    points: list[tuple[float, float, float]]  # 17 entries

    @property
    def left_wrist(self) -> tuple[float, float, float]:
        return self.points[9]

    @property
    def right_wrist(self) -> tuple[float, float, float]:
        return self.points[10]

    @property
    def left_shoulder(self) -> tuple[float, float, float]:
        return self.points[5]

    @property
    def right_shoulder(self) -> tuple[float, float, float]:
        return self.points[6]
    # ... more accessors as needed

class Detection(BaseModel):
    frame_index: int
    timestamp_sec: float
    bbox: BBox
    class_name: str
    confidence: float
    track_id: Optional[int] = None
    keypoints: Optional[Keypoints] = None

class Track(BaseModel):
    track_id: int
    class_name: str
    detections: list[Detection]  # sorted by frame_index

    @property
    def start_time(self) -> float:
        return self.detections[0].timestamp_sec

    @property
    def end_time(self) -> float:
        return self.detections[-1].timestamp_sec

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
```

The **vision layer** produces a `list[Track]`. Everything else consumes it.

---

## 7. Pipeline Execution — How JSON Becomes a Running Script

This is the core execution engine. It takes a validated `AnalysisPlan` and runs it.

### 7.1 — The Pipeline Runner (Pseudocode)

```python
# backend/app/pipeline/runner.py

from app.vision.detector import run_detection_and_tracking
from app.vision.pose import run_pose_tracking
from app.core.decode import decode_video
from app.pipeline.filters import apply_filters
from app.pipeline.registry import TASK_REGISTRY

async def run_pipeline(video_path: str, plan: AnalysisPlan, roi_polygon: list | None):
    """
    Execute the full pipeline from plan JSON to results.
    
    Returns:
        {
            "events": [...],
            "aggregates": {...},
            "timeline": [...],
            "metadata": { "frames_processed": N, "tracks_found": M, ... }
        }
    """

    # ── Step 1: Decode ──
    video_meta = decode_video(video_path)
    fps = video_meta["fps"]
    frame_count = video_meta["frame_count"]

    # ── Step 2: Vision (YOLO detect + track, optional pose) ──
    vision_config = plan.vision

    if vision_config.enable_pose:
        tracks, secondary_detections = run_pose_tracking(
            video_path=video_path,
            model_name=vision_config.model,
            detect_classes=vision_config.detect_classes,
            confidence=vision_config.confidence_threshold,
            sample_fps=vision_config.sample_fps,
        )
    else:
        tracks, secondary_detections = run_detection_and_tracking(
            video_path=video_path,
            model_name=vision_config.model,
            detect_classes=vision_config.detect_classes,
            confidence=vision_config.confidence_threshold,
            sample_fps=vision_config.sample_fps,
        )

    # `tracks` = list[Track] for the primary object (e.g. person)
    # `secondary_detections` = list[Detection] for secondary objects
    #   (e.g. dining table, cell phone) — used by object_association filter

    # ── Step 3: Filter ──
    filtered_tracks = apply_filters(
        tracks=tracks,
        filters=plan.filters,
        roi_polygon=roi_polygon if plan.use_roi else None,
        secondary_detections=secondary_detections,
        fps=fps,
    )

    # ── Step 4: Metric ──
    task_fn = TASK_REGISTRY[plan.task]
    result = task_fn(
        tracks=filtered_tracks,
        params=plan.params,
        roi_polygon=roi_polygon if plan.use_roi else None,
        fps=fps,
        video_duration=video_meta["duration"],
    )

    # ── Step 5: Format ──
    output = format_result(result, plan.output)

    return output
```

### 7.2 — The Task Registry

```python
# backend/app/pipeline/registry.py

from app.metrics.dwell import compute_dwell_count
from app.metrics.traffic import compute_traffic_count
from app.metrics.interval import compute_count_per_interval
from app.metrics.occupancy import compute_occupancy
from app.metrics.exit_reentry import compute_exit_reentry
from app.metrics.pose_events import compute_pose_event_count
from app.metrics.object_dwell import compute_object_co_occurrence_dwell

# Maps task name → function
TASK_REGISTRY: dict[str, callable] = {
    "dwell_count": compute_dwell_count,
    "traffic_count": compute_traffic_count,
    "count_per_interval": compute_count_per_interval,
    "occupancy": compute_occupancy,
    "exit_reentry": compute_exit_reentry,
    "pose_event_count": compute_pose_event_count,
    "object_co_occurrence_dwell": compute_object_co_occurrence_dwell,
}

def get_task_docs() -> str:
    """Return task descriptions for the LLM system prompt."""
    docs = []
    for name, fn in TASK_REGISTRY.items():
        docs.append(f"- {name}: {fn.__doc__.strip().split(chr(10))[0]}")
    return "\n".join(docs)
```

### 7.3 — The Filter Pipeline

Filters run in a defined order. Each is a pure function: tracks in, tracks out.

```python
# backend/app/pipeline/filters.py

from shapely.geometry import Point, Polygon

def apply_filters(tracks, filters, roi_polygon, secondary_detections, fps):
    result = tracks

    # 1. Track quality filter (always runs)
    result = filter_by_min_frames(result, filters.min_track_frames)
    result = filter_by_confidence(result, filters.min_confidence)

    # 2. ROI spatial filter (if ROI exists)
    if roi_polygon is not None:
        polygon = Polygon([(p["x"], p["y"]) for p in roi_polygon])
        result = filter_by_roi(result, polygon, mode=filters.roi_mode)

    # 3. Appearance filter (if specified)
    if filters.appearance is not None:
        result = filter_by_appearance(result, filters.appearance)

    # 4. Object association (if specified)
    if filters.object_association is not None:
        result = filter_by_object_association(
            result, secondary_detections, filters.object_association
        )

    return result
```

### 7.4 — The API Endpoint

```python
# In backend/app/main.py

@app.post("/api/video/{video_id}/analyze")
async def analyze_video(video_id: str, request: AnalyzeRequest):
    """
    Full pipeline: prompt → plan → vision → metrics → results.
    
    Body: { "prompt": "How many people loiter...?" }
       OR { "plan": { ... } }  (if user edited the plan directly)
    """
    video_path = f"uploads/{video_id}.mp4"

    # Load ROI if exists
    roi_polygon = load_roi(video_id)

    if request.prompt and not request.plan:
        # Step A: LLM generates plan from prompt
        plan_json = await generate_plan(request.prompt, video_id, roi_polygon)
        plan = AnalysisPlan.model_validate(plan_json)
    else:
        plan = AnalysisPlan.model_validate(request.plan)

    # Step B: Run pipeline
    result = await run_pipeline(video_path, plan, roi_polygon)

    return {
        "plan": plan.model_dump(),
        "result": result,
    }
```

### 7.5 — Separation of Concerns: Why the LLM Never Runs Code

```
┌──────────────────────────────────────────────────────────────┐
│  LLM  ─── produces JSON plan ───►  VALIDATOR  ── rejects    │
│                                       │           bad plans  │
│                                       ▼                      │
│                               PIPELINE RUNNER                │
│                            (fixed Python code)               │
│                                       │                      │
│                   ┌───────────────────┼───────────────┐      │
│                   ▼                   ▼               ▼      │
│              YOLO detect        ROI filter       Metric fn   │
│           (fixed library)    (fixed logic)    (fixed logic)  │
└──────────────────────────────────────────────────────────────┘

The LLM's output is DATA (JSON), never CODE.
The pipeline runner interprets the data to call fixed functions.
```

This means:
- The LLM cannot execute arbitrary code.
- Every task/filter/vision option is a known, tested function.
- The system is secure and predictable.
- New capabilities = new registered modules, not new LLM powers.

---

## 8. Metric Modules — The Primitives

Each metric is a standalone function with a clear signature. Listed in implementation priority order.

### 8.1 — `dwell_count` (Implement First)

**What it does:** For each track, compute how long its center point stays inside the ROI. Emit events for tracks that dwell >= threshold.

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `dwell_threshold_seconds` | float | 5.0 | Min seconds inside ROI to count as "dwelling" |
| `jitter_tolerance_px` | int | 15 | Ignore brief exits < this distance from polygon edge |
| `report_per_track` | bool | false | If true, include per-track dwell time in events |
| `group_by` | string\|null | null | `"associated_object"` to group by table/zone |

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

**Logic sketch:**

```python
def compute_dwell_count(tracks, params, roi_polygon, fps, video_duration):
    polygon = Polygon([(p["x"], p["y"]) for p in roi_polygon]) if roi_polygon else None
    threshold = params.get("dwell_threshold_seconds", 5.0)
    events = []

    for track in tracks:
        # Compute per-frame in/out
        inside_frames = []
        for det in track.detections:
            pt = Point(det.bbox.center)
            if polygon is None or polygon.contains(pt):
                inside_frames.append(det.frame_index)

        # Find contiguous runs of "inside" frames
        runs = find_contiguous_runs(inside_frames)

        for run_start, run_end in runs:
            duration = (run_end - run_start) / fps
            if duration >= threshold:
                events.append({
                    "type": "dwell",
                    "track_id": track.track_id,
                    "start_time_sec": run_start / fps,
                    "end_time_sec": run_end / fps,
                    "duration_sec": duration,
                    "frame_start": run_start,
                    "frame_end": run_end,
                })

    aggregates = {
        "total_dwellers": len(set(e["track_id"] for e in events)),
        "average_dwell_seconds": mean([e["duration_sec"] for e in events]) if events else 0,
        "max_dwell_seconds": max([e["duration_sec"] for e in events]) if events else 0,
    }

    return {"events": events, "aggregates": aggregates}
```

---

### 8.2 — `traffic_count` (Implement Second)

**What it does:** Count unique tracks that enter/cross/pass through the ROI.

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `count_mode` | string | `"unique_entries"` | `"unique_entries"` (first entry per track), `"unique_crossings"` (track enters then exits), `"first_entry_only"` (intrusion: first-ever entry per track) |

**Returns:**

```json
{
  "events": [
    {
      "type": "entry",
      "track_id": 3,
      "time_sec": 5.2,
      "frame": 156,
      "direction": "in"
    }
  ],
  "aggregates": {
    "total_count": 42,
    "entries": 42,
    "exits": 38
  }
}
```

---

### 8.3 — `occupancy`

**What it does:** Per time slice, count how many track IDs have their center inside the ROI.

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `time_resolution_seconds` | float | 1.0 | Granularity of the time series |

**Returns:**

```json
{
  "events": [],
  "aggregates": {
    "peak_occupancy": 12,
    "peak_time_sec": 145.0,
    "average_occupancy": 6.3
  },
  "timeline": [
    { "time_sec": 0, "count": 3 },
    { "time_sec": 1, "count": 4 },
    { "time_sec": 2, "count": 5 }
  ]
}
```

---

### 8.4 — `count_per_interval`

**What it does:** Bucket traffic/crossing counts into time windows; compute per-window count and average.

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `interval_source` | string | `"fixed_seconds"` | `"fixed_seconds"` or `"manual_markers"` (future) |
| `interval_seconds` | float | 60.0 | Window size in seconds |
| `aggregation` | string | `"average"` | `"average"`, `"sum"`, `"max"`, `"min"` |
| `count_mode` | string | `"unique_crossings"` | Same as traffic_count modes |

---

### 8.5 — `exit_reentry`

**What it does:** Find tracks that leave the ROI and then come back.

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `min_time_outside_seconds` | float | 2.0 | Ignore exits shorter than this (prevents jitter) |

**Returns:**

```json
{
  "events": [
    {
      "type": "exit_reentry",
      "track_id": 5,
      "exit_time_sec": 30.2,
      "reentry_time_sec": 45.8,
      "time_outside_sec": 15.6,
      "exit_frame": 906,
      "reentry_frame": 1374
    }
  ],
  "aggregates": {
    "tracks_with_reentry": 3,
    "average_time_outside_sec": 12.1
  }
}
```

---

### 8.6 — `pose_event_count` (Requires Pose Model)

**What it does:** Count discrete pose events (hand raise, wave, punch) per track.

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `pose_event` | string | — | Event name: `"hand_raise"`, `"wave"`, `"punch"`, `"crouch"` |
| `min_hold_frames` | int | 3 | Minimum frames the pose must be held to count as one event |

**Pose event definitions (hardcoded rules):**

```python
POSE_EVENT_RULES = {
    "hand_raise": lambda kp: (
        kp.left_wrist[1] < kp.left_shoulder[1] - 30  # wrist above shoulder
        or kp.right_wrist[1] < kp.right_shoulder[1] - 30
    ),
    "wave": lambda kp: (
        # wrist above shoulder + horizontal displacement
        (kp.right_wrist[1] < kp.right_shoulder[1] - 20)
        and abs(kp.right_wrist[0] - kp.right_shoulder[0]) > 40
    ),
    "punch": lambda kp: (
        # arm fully extended forward (elbow nearly straight, wrist far from shoulder)
        distance(kp.right_wrist, kp.right_shoulder) > 150
        or distance(kp.left_wrist, kp.left_shoulder) > 150
    ),
    "crouch": lambda kp: (
        # hip close to knee height
        abs(kp.left_hip[1] - kp.left_knee[1]) < 40
    ),
}
```

These rules are deliberately simple. They can be refined with real data. The key point is they are **fixed in code**, not generated by the LLM.

---

### 8.7 — `object_co_occurrence_dwell` (Requires Multi-Class Detection)

**What it does:** Time that a primary object (person) is associated with a secondary object (cell phone, dining table).

**Params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `report_per_track` | bool | true | Report per-track breakdown |

**Logic:** For each frame of a person track, check if any secondary object detection overlaps/is proximate. Sum frames where association holds → convert to seconds.

---

## 9. Filter System — Appearance, Object Co-occurrence, Pose

### 9.1 — ROI Spatial Filter

Uses `shapely.Polygon.contains(Point)` for point-in-polygon. Four modes:

| Mode | Logic |
|------|-------|
| `inside` | Keep detections where bbox center is inside polygon |
| `enters` | Detect transition from outside→inside per track; emit entry events |
| `crosses` | Track was both inside and outside polygon at some point |
| `outside` | Keep detections where bbox center is outside polygon |

### 9.2 — Appearance Filter (Color)

**How it works:**

1. For each track, take a representative frame (or sample every N frames).
2. Crop the bbox from the frame.
3. Isolate the `color_region` (e.g. "torso" = top 40-60% of bbox height; "lower" = bottom 40%).
4. Convert crop to HSV.
5. Compute dominant hue via histogram or KMeans.
6. Compare against target color's HSV range.

**Color → HSV mapping (predefined):**

```python
COLOR_HSV_RANGES = {
    "red":    [(0, 70, 70), (10, 255, 255)],    # + wrapping at 170-180
    "orange": [(10, 70, 70), (25, 255, 255)],
    "yellow": [(25, 70, 70), (35, 255, 255)],
    "green":  [(35, 70, 70), (85, 255, 255)],
    "blue":   [(85, 70, 70), (130, 255, 255)],
    "purple": [(130, 70, 70), (170, 255, 255)],
    "white":  [(0, 0, 180), (180, 40, 255)],
    "black":  [(0, 0, 0), (180, 255, 50)],
}
```

**Match threshold:** If >= 20% of pixels in the region fall within the target HSV range, the track passes. Threshold is tunable.

### 9.3 — Object Association Filter

**Used for:** "person at table", "person with phone", etc.

**How it works:**

1. Vision detects both primary (person) and secondary (table, phone) objects.
2. For each person detection in each frame, check all secondary detections in the same frame.
3. Association methods:
   - **bbox_overlap:** IoU > 0 between person bbox and secondary bbox.
   - **proximity:** Euclidean distance between centers < `max_distance_px`.
   - **containment:** Person center is inside secondary bbox (or vice versa).
4. A person track "has association" if association holds for >= N frames.

---

## 10. Output Contract — What Every Pipeline Returns

Every metric function returns this structure:

```python
class PipelineResult(BaseModel):
    events: list[dict]       # Timestamped events (dwell, entry, exit, pose, etc.)
    aggregates: dict         # Summary stats (count, avg, max, etc.)
    timeline: list[dict]     # Per-time-slice data for charts (optional)
    metadata: dict           # Processing info (frames_processed, tracks_found, etc.)
```

The `/api/video/{video_id}/analyze` endpoint returns:

```json
{
  "plan": { "...the validated plan that was executed..." },
  "result": {
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
      "average_dwell_seconds": 8.2
    },
    "timeline": [
      { "time_sec": 0, "occupancy": 3 },
      { "time_sec": 1, "occupancy": 4 }
    ],
    "metadata": {
      "frames_processed": 1800,
      "tracks_found": 47,
      "tracks_after_filter": 14,
      "processing_time_sec": 12.3,
      "model_used": "yolo26n",
      "video_duration_sec": 60.0
    }
  }
}
```

This feeds the frontend:
- **`events`** → Event timeline (click to jump to timestamp in video)
- **`aggregates`** → Headline metrics cards
- **`timeline`** → Charts (occupancy over time, counts per interval)
- **`plan`** → Editable plan pane (user can modify and re-run)

---

## 11. Caching Strategy

Vision is the expensive step (~5-30 seconds depending on video length). Metrics are cheap (< 1 second on cached tracks). Cache aggressively.

### Cache Key Structure

```
cache/
└── {video_hash}/
    └── {model}_{classes}_{confidence}_{sample_fps}/
        ├── tracks.json          # All Track objects serialized
        ├── secondary.json       # Secondary detections (tables, phones, etc.)
        ├── pose_tracks.json     # Tracks with keypoints (if pose was enabled)
        └── metadata.json        # Vision run metadata
```

### Cache Logic

```python
def get_or_run_vision(video_path, vision_config):
    cache_key = compute_cache_key(video_path, vision_config)
    
    if cache_exists(cache_key):
        return load_from_cache(cache_key)
    
    tracks, secondary = run_vision(video_path, vision_config)
    save_to_cache(cache_key, tracks, secondary)
    return tracks, secondary
```

**Result:** Changing the prompt (different metric or filter) re-runs only the cheap metric step if vision config hasn't changed. Tweaking a dwell threshold from 5s to 10s? Instant — reuse cached tracks, re-run `dwell_count` only.

---

## 12. Implementation Order — One Section at a Time

Build **one phase at a time**. After each phase: **test thoroughly**, then **add flexibility** (e.g. one more metric or one more param) as you progress. Do not start the next phase until the current one is stable and you’ve validated behavior on real videos.

---

### Phase 1: Foundation — One Metric End-to-End (No LLM Yet)

**Goal:** Run a single metric (`dwell_count`) on a real video with a drawn ROI, using a **hardcoded** plan. No natural language, no planner.

| Step | What to Build | How to Test | Files |
|------|---------------|-------------|-------|
| **1a** | Add Ultralytics (and Shapely) to requirements. Use **YOLO26** if available (`yolo26n.pt`); fallback to `yolo11n.pt` if your `ultralytics` version doesn’t have YOLO26 yet. | In Python: `from ultralytics import YOLO; m = YOLO("yolo26n.pt")` (or `yolo11n.pt`) loads without error. | `backend/requirements.txt` |
| **1b** | Vision: `detector.py` + `models.py`. Run YOLO `.track()` on a video path; return `list[Track]` in the format from Section 6.5. | Script or test: pass a short video, get back tracks with stable IDs; log track count and a few bboxes. | `backend/app/vision/detector.py`, `models.py` |
| **1c** | ROI filter: point-in-polygon with Shapely. Function: `filter_tracks_by_roi(tracks, polygon, mode="inside")`. | Unit test: synthetic polygon + list of detections with known centers → correct in/out. | `backend/app/pipeline/filters.py` |
| **1d** | Metric: `dwell_count(tracks, roi_polygon, params, fps)`. Returns `{ events, aggregates }` as in Section 8.1. | Unit test: feed fake tracks + ROI, assert correct dwell events and counts for known inputs. | `backend/app/metrics/dwell.py` |
| **1e** | Pipeline runner: decode → vision → filter by ROI → dwell_count. Accept a **hardcoded** plan dict (only `dwell_count` + `use_roi`). | E2E: upload video, draw ROI, call runner with fixed plan → get result with events and aggregates. | `backend/app/pipeline/runner.py` |
| **1f** | API: `POST /api/video/{id}/analyze` with body `{ "plan": { ... } }`. Load ROI for that video; if plan has `use_roi` and no ROI, return `needs_roi` (see Section 5.6). Otherwise run pipeline and return results. | From frontend or curl: with ROI present, send hardcoded dwell_count plan → 200 and result JSON. Without ROI → 200 with `status: "needs_roi"`. | `backend/app/main.py` |

**Checkpoint:** Upload a video, draw an ROI, trigger analyze with a fixed dwell plan. You should see real dwell events and counts. **Then** consider small flexibility: e.g. make `dwell_threshold_seconds` configurable in the plan and pass it through to the metric.

---

### Phase 2: LLM Planning + ROI Instruction

**Goal:** User types a question → LLM returns a validated plan (and optional `roi_instruction`). Pipeline still runs the same way; only the source of the plan changes.

| Step | What to Build | How to Test | Files |
|------|---------------|-------------|-------|
| **2a** | Pydantic schema for the plan (Section 2 + 5.5). Include `roi_instruction: Optional[str]`. Validate `task`, `vision`, `filters`, `params`. | Construct valid and invalid JSON; assert valid parses, invalid raises. | `backend/app/pipeline/schema.py` |
| **2b** | LLM planner: system prompt (schema + task list + rule to output `roi_instruction` when `use_roi` is true) + API call → plan JSON. | Prompt: "How many people loiter for 10 seconds?" → plan with `task: dwell_count`, `use_roi: true`, and a sensible `roi_instruction`. | `backend/app/planner/llm.py` |
| **2c** | `/analyze` accepts `{ "prompt": "..." }`. Call planner → validate plan. If `use_roi` and no ROI for video → return `status: "needs_roi"`, `plan`, `roi_instruction`. Else run pipeline and return `status: "ok"`, `result`. | With ROI: prompt → plan + result. Without ROI: prompt → `needs_roi` + plan + `roi_instruction` (e.g. "Draw an ROI in front of the store."). | `backend/app/main.py` |
| **2d** | Frontend: On Run, send prompt. If response is `needs_roi`, show message + **roi_instruction** and a "Draw ROI" CTA. If `ok`, show plan + results. | Run without ROI → see instruction and button; draw ROI, run again → see results. | `components/workspace/intent-pane.tsx`, `evidence-pane.tsx`, `results-pane.tsx` |

**Checkpoint:** Ask "How many people loiter in front of my store?" with no ROI → see contextual instruction. Draw ROI and run again → get real results. **Flexibility:** Add 1–2 more prompt examples to the planner and confirm the right task and params are chosen.

---

### Phase 3: More Metrics (Add One at a Time)

**Goal:** Support more tasks so more prompts work. Add **one metric at a time**, test it, then add the next.

| Step | What to Build | How to Test | Files |
|------|---------------|-------------|-------|
| **3a** | `traffic_count`: unique tracks entering (or crossing) ROI. Register in registry; add params to schema. | Unit test + E2E with a plan that uses `traffic_count`. Prompt: "How many people get on the bus?" (with ROI on door). | `backend/app/metrics/traffic.py`, `registry.py`, `schema.py` |
| **3b** | `occupancy`: count distinct track IDs inside ROI per time slice; peak + timeline. | Unit test + E2E. Prompt: "How many people in the store at peak?" | `backend/app/metrics/occupancy.py` |
| **3c** | `count_per_interval`: bucket traffic by fixed windows; average count per interval. | Unit test + E2E. Prompt: "Average number crossing at each red light" (use fixed 90s for now). | `backend/app/metrics/interval.py` |
| **3d** | `exit_reentry`: tracks that leave ROI then re-enter. | Unit test + E2E. Prompt: "People who leave then come back." | `backend/app/metrics/exit_reentry.py` |
| **3e** | Update LLM system prompt: add each new task name, param spec, and one example per task. | Run 4–5 different prompts; each should map to the right task and run without errors. | `backend/app/planner/llm.py` |

**Checkpoint:** Each new metric works for at least one real prompt and one video. **Flexibility:** Tune params (e.g. `min_track_frames`, `interval_seconds`) via the plan and re-run without code changes.

---

### Phase 4: Pose + Appearance (Optional, When You Need Them)

**Goal:** Support pose-based queries (hand raise, punch) and simple appearance (e.g. "person in green shirt"). Add only when you’re ready to test pose/color on real footage.

| Step | What to Build | How to Test | Files |
|------|---------------|-------------|-------|
| **4a** | Pose module: load `yolo26n-pose.pt` (or `yolo11n-pose.pt`), run track, attach keypoints to detections. Same `Track` structure. | Run on short clip; inspect tracks have keypoints. | `backend/app/vision/pose.py` |
| **4b** | `pose_event_count`: rules for hand_raise, punch, etc. (Section 8.6). Register task. | Unit test with mock keypoints; E2E with "person raises hand" prompt. | `backend/app/metrics/pose_events.py` |
| **4c** | Appearance filter: color from bbox crop, match to named color. Use in filter pipeline when `filters.appearance` is set. | Unit test: fake track + frame crop; assert pass/fail for color. E2E with "person in green shirt" prompt. | `backend/app/vision/color.py`, `pipeline/filters.py` |
| **4d** | Object association filter: person ↔ table or person ↔ phone. | Test with video that has tables or phones; plan with `object_association`. | `backend/app/vision/association.py` |
| **4e** | `object_co_occurrence_dwell` (e.g. time on phone). Register and add to prompt. | E2E: "Time this person spends on phone" (optional appearance filter). | `backend/app/metrics/object_dwell.py` |

**Checkpoint:** At least one pose prompt and one appearance prompt work end-to-end. **Flexibility:** Add one new pose event (e.g. "wave") or one new color as you need.

---

### Phase 5: Polish + Caching

**Goal:** Faster re-runs, better UX, and evidence linking.

| Step | What to Build | How to Test | Files |
|------|---------------|-------------|-------|
| **5a** | Vision cache: key by (video hash, model, classes, confidence, sample_fps). Save/load tracks to disk. Runner uses cache when config matches. | Run same video twice; second run skips vision and uses cache. Change param (e.g. dwell threshold) → only metric re-runs. | `backend/app/pipeline/cache.py` |
| **5b** | Progress: SSE or polling endpoint for "analyzing… step 2/4". | Frontend shows progress during long runs. | `backend/app/main.py` |
| **5c** | Annotated frames: draw bboxes + track IDs on frames for event timestamps. Optional. | Evidence pane can show a frame per event. | `backend/app/vision/annotate.py` |
| **5d** | Event explorer: click event → seek video to that timestamp. | Click dwell event → video jumps to start of dwell. | `components/workspace/results-pane.tsx` |
| **5e** | Editable plan: show plan JSON in intent pane; user can tweak and re-run. | Change dwell_seconds in plan, re-run → different results. | `components/workspace/intent-pane.tsx` |

**Checkpoint:** Re-runs are fast when only params change; users can jump to evidence and edit the plan. **Flexibility:** Add more output options (e.g. `include_timeline: false`) or more annotated frame types as needed.

---

### How to Use This Order

- **One phase at a time:** Finish Phase 1 (including checkpoint and one small flexibility) before starting Phase 2. Same for 2 → 3 → 4 → 5.
- **Test as you go:** Prefer one concrete test per step (unit or E2E). If a step is large, split it and test after each sub-step.
- **Add flexibility incrementally:** After each phase, add one thing that makes the system more flexible (e.g. one more param, one more task, or one more prompt example) and validate before moving on. That way the system grows in small, testable increments.

---

## 13. Extending the System — Adding New Capabilities

### Adding a New Metric

1. Write the function in `backend/app/metrics/my_new_metric.py`:
   ```python
   def compute_my_metric(tracks, params, roi_polygon, fps, video_duration):
       """One-line description for LLM system prompt."""
       # ... logic ...
       return {"events": [...], "aggregates": {...}}
   ```
2. Register it in `TASK_REGISTRY`:
   ```python
   TASK_REGISTRY["my_metric"] = compute_my_metric
   ```
3. Add its name to the `TaskName` enum in the Pydantic schema.
4. Add a few-shot example to the LLM system prompt.
5. Done. The LLM can now select it, the validator will accept it, and the runner will execute it.

### Adding a New Pose Event

1. Add a rule to `POSE_EVENT_RULES` in `backend/app/metrics/pose_events.py`:
   ```python
   "new_action": lambda kp: (some condition on keypoints)
   ```
2. Add the event name to the allowed values in the schema.
3. Add a few-shot example to the LLM system prompt.

### Adding a New Appearance Filter

1. Add color HSV ranges to `COLOR_HSV_RANGES` (or add a new filter type like "pattern" or "clothing type").
2. If it needs a new model (e.g. clothing classifier), add it to `backend/app/vision/` and integrate into the filter pipeline.

### Adding a New Object Association

1. The YOLO COCO model already detects 80 classes. If the secondary object is in COCO, just add its name to `detect_classes` and configure `object_association` in the plan.
2. If it's not in COCO (e.g. a custom object), you'd need to fine-tune or use a different model. That's a larger effort but the pipeline architecture supports it: swap the model in the vision module.

### The System's Flexibility Principle

```
 ┌────────────────────────────────────────────────────┐
 │  New user prompt                                    │
 │  "How many people wave at the camera?"              │
 ├────────────────────────────────────────────────────┤
 │  Q: Does a task exist?                              │
 │     → Yes (pose_event_count)                        │
 │  Q: Does a pose event rule exist?                   │
 │     → No ("wave" not defined)                       │
 │  Action: Add wave rule to POSE_EVENT_RULES          │
 │          (5 lines of code)                          │
 │  Now the prompt works end-to-end.                   │
 └────────────────────────────────────────────────────┘

 ┌────────────────────────────────────────────────────┐
 │  New user prompt                                    │
 │  "Speed of each car passing through"                │
 ├────────────────────────────────────────────────────┤
 │  Q: Does a task exist?                              │
 │     → No (no "speed" metric)                        │
 │  Action: Write compute_speed() metric module        │
 │          (track displacement / time between frames)  │
 │          Register in TASK_REGISTRY                   │
 │          Add to schema + LLM prompt                  │
 │  Now the prompt works end-to-end.                   │
 └────────────────────────────────────────────────────┘
```

Every new capability is either:
- **Zero code:** The existing primitives already cover it (LLM just picks the right combination).
- **Minimal code:** Add one rule, one HSV range, or one small function.
- **One module:** Write a new metric function with the standard signature.

The pipeline architecture stays the same. The JSON schema grows additively. The LLM learns new tasks via updated system prompts. This is how all the PLANNING.md examples become achievable over time without rewriting the system.

---

## Appendix A: Updated `requirements.txt`

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
opencv-python==4.8.1.78
numpy==1.24.3
ultralytics>=8.3.0
shapely>=2.0.0
openai>=1.0.0
pydantic>=2.0.0
```

## Appendix B: Full Backend Folder Structure (Target State)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app + endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   └── decode.py              # Video → frames, fps, metadata
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── detector.py            # YOLO detect + track
│   │   ├── pose.py                # YOLO-Pose keypoints
│   │   ├── color.py               # Color extraction from crops
│   │   ├── association.py         # Object-to-object association
│   │   └── models.py              # Track, Detection, BBox, Keypoints
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── dwell.py               # dwell_count
│   │   ├── traffic.py             # traffic_count
│   │   ├── occupancy.py           # occupancy
│   │   ├── interval.py            # count_per_interval
│   │   ├── exit_reentry.py        # exit_reentry
│   │   ├── pose_events.py         # pose_event_count
│   │   └── object_dwell.py        # object_co_occurrence_dwell
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── runner.py              # Orchestrates decode → vision → filter → metric
│   │   ├── registry.py            # TASK_REGISTRY mapping
│   │   ├── filters.py             # ROI, appearance, association filters
│   │   ├── schema.py              # Pydantic AnalysisPlan model
│   │   └── cache.py               # Vision result caching
│   ├── planner/
│   │   ├── __init__.py
│   │   └── llm.py                 # LLM system prompt + API call → plan JSON
│   └── storage/
│       └── roi_storage.json
├── cache/                          # Cached vision outputs (gitignored)
├── uploads/                        # Uploaded videos (gitignored)
├── requirements.txt
└── README.md
```
