# LinkedIn Launch Review — Current State & Final Polish

**Date:** February 2026  
**Purpose:** Honest audit of what the system can answer right now, what the visible gaps are,
and a prioritized list of high-impact, low-effort improvements to make before posting.

---

## Table of Contents

1. [What the System Can Answer Today](#what-the-system-can-answer-today)
2. [What It Cannot Answer (Honest Gaps)](#what-it-cannot-answer-honest-gaps)
3. [The ROI-Required Problem](#the-roi-required-problem)
4. [Recommended Final Polish (Ranked)](#recommended-final-polish-ranked)
5. [The "Green Shirt" Feature — No-ROI Appearance Queries](#the-green-shirt-feature--no-roi-appearance-queries)
6. [What NOT to Add Before Launch](#what-not-to-add-before-launch)

---

## What the System Can Answer Today

### Category 1: Dwell / Loitering (Timing Queries)

These all use `dwell_count` with ROI required.

| Question | Works? | Notes |
|----------|--------|-------|
| "How many people loiter for 5+ seconds?" | ✅ | threshold extracted from prompt |
| "How many cars linger in the AOI for more than 10 seconds?" | ✅ | works for any YOLO class |
| "What is the average dwell time at the entrance?" | ✅ | avg_dwell_seconds in aggregates |
| "How long do people wait in the queue?" | ✅ | threshold=0 reports all waits |
| "Who stops to look at the display for 3+ seconds?" | ✅ | threshold extracted |
| "What is the maximum time anyone spent in the zone?" | ✅ | max_dwell_seconds in aggregates |
| "What is the minimum dwell time?" | ✅ | min_dwell_seconds in aggregates |
| "How many unique people dwelled?" | ✅ | total_dwellers aggregate |
| "How many dwell events occurred?" | ✅ | total_dwell_events aggregate |
| "How long does a typical customer spend near the display?" | ✅ | avg_dwell_seconds |
| "Are there any dogs that stay in the yard for 30+ seconds?" | ✅ | object = "dog", COCO class |
| "How long do cars idle at the intersection?" | ✅ | object = "car", threshold=0 |

**What the output looks like:**
- Headline metrics: `Total Dwellers`, `Total Dwell Events`, `Avg Dwell`, `Max Dwell`, `Min Dwell`
- Event cards: per-track with `Track ID`, duration, and `start → end` timestamps
- Annotated video: bboxes color-coded red (outside ROI) → yellow (inside, not yet qualified) → green (dwell threshold met)

---

### Category 2: Traffic / Counting (Entry–Exit Queries)

These all use `traffic_count` with ROI required.

| Question | Works? | Notes |
|----------|--------|-------|
| "How many people enter the store?" | ✅ | roi_mode: enters |
| "How many people exit the store?" | ✅ | roi_mode: exits |
| "How many people cross the crosswalk?" | ✅ | roi_mode: crosses |
| "Count cars entering the parking lot" | ✅ | object = "car" |
| "How many people crossed in total?" | ✅ | unique_crossings aggregate |
| "Did more people enter or exit?" | ✅ | run both modes, compare |
| "How many buses entered the depot?" | ✅ | object = "bus", YOLO COCO class |
| "How many cyclists passed the checkpoint?" | ✅ | object = "bicycle" |

**What the output looks like:**
- Headline metric: `Unique Entries` OR `Unique Exits` OR `Unique Crossings` (mode-specific, no clutter)
- Event cards: per-event with `Track ID`, "entered"/"exited" badge, and timestamp
- Annotated video: bboxes stay green permanently once the qualifying transition is detected

---

### Category 3: Object Class Flexibility

Because YOLO11n is trained on all 80 COCO classes, any of these objects work without code changes:

> person, car, truck, bus, bicycle, motorcycle, dog, cat, bird, horse, sheep, cow,
> elephant, bear, sports ball, bottle, cup, cell phone, laptop, chair, dining table,
> couch, bed, backpack, umbrella, suitcase, and 55 more.

The LLM planner already picks up on object references in the prompt and sets `detect_classes` accordingly. So "how many dogs linger near the gate" works exactly as well as "how many people."

---

### Category 4: Combined Behaviors (Via Prompt Phrasing)

The LLM is flexible enough to handle these phrasings on the existing two tasks:

| Prompt Style | What Happens |
|--------------|-------------|
| "Any trucks idling for more than 2 minutes?" | dwell_count, object=truck, threshold=120 |
| "Who was near the cash register the longest?" | dwell_count, max_dwell from events tells you |
| "How many people walked through the doorway?" | traffic_count, roi_mode=crosses |
| "How many intrusions in the restricted zone?" | traffic_count, count_mode=unique_entries |
| "Anyone loiter for more than 0 seconds?" | dwell_count, threshold=0 (every contact) |

---

## What It Cannot Answer (Honest Gaps)

| Question | Why It Fails |
|----------|-------------|
| "How many people have a green shirt?" | No appearance/color filter — ROI-free whole-video queries not supported |
| "Count people wearing red" | Same — no HSV color extraction from track crops |
| "How many times did someone check their phone?" | No object association, no transition-counting on secondary objects |
| "Which table had the longest seated customer?" | No multi-object association or group_by |
| "How many sips of water did she take?" | No object interaction counting |
| "Average time before a customer picks up a product?" | No object proximity logic |
| "How many people were in the store at once?" | Occupancy removed from plan — per-frame counting not built |
| "Is the parking lot more than 50% full?" | Same — occupancy not built |
| "Average crossings per green light?" | No time-windowing (count_per_interval not built) |
| "Did anyone enter *and* come back?" | exit_reentry not built |
| "How many people raised their hand?" | No pose model |
| "Count people on the phone, not in any specific zone" | No ROI-free whole-video detection mode |

---

## The ROI-Required Problem

**This is the most visible UX gap for a demo.**

Right now, almost every query requires drawing an ROI polygon first. This means:

1. User uploads video
2. User must click "Draw ROI", open the canvas, draw a polygon, save it
3. Only then can they ask a question

For many legitimate, impressive queries, no zone is conceptually needed:

- "How many people are in this video?" — whole frame, no zone
- "Count all cars that appear" — no zone needed
- "How many people have a green shirt?" — no zone needed
- "Count dogs" — no zone needed

**The root cause:** The pipeline's `use_roi: false` path *does exist* — `runner.py` line 99 handles it:

```python
effective_roi = roi_polygon if use_roi else None
```

And `dwell_count` already handles `roi_polygon=None` gracefully (treats all detections as inside). So the backend already supports no-ROI queries — but the LLM almost always sets `use_roi: true` because every example in the system prompt uses it.

**Fix: Add no-ROI examples to the LLM system prompt.** That alone would unlock whole-video queries.

---

## Recommended Final Polish (Ranked)

These are ordered by impact-to-effort ratio. All are **1-2 hour tasks** max.

---

### 🥇 Fix 1: Add No-ROI Query Support (1 hour, very high impact)

**Problem:** "Count all cars in the video" fails or produces wrong results because the LLM always generates `use_roi: true`, then shows "needs_roi" dialog.

**Fix:** Add examples to `llm.py` system prompt for no-ROI queries:

```python
# Add to SYSTEM_PROMPT_TEMPLATE examples section:

Prompt: "How many people appear in this video?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count all people with no ROI — use_roi: false, threshold 0 to count every appearance."}}

Prompt: "Count all cars in the video"
Plan:
{{"task": "dwell_count", "object": "car", "use_roi": false, "vision": {{"detect_classes": ["car"]}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count all cars in frame — no zone required, threshold 0."}}

Prompt: "How many dogs are visible?"
Plan:
{{"task": "dwell_count", "object": "dog", "use_roi": false, "vision": {{"detect_classes": ["dog"]}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count all dogs visible, no spatial restriction."}}
```

Also add a rule:
```
7. If the user does NOT mention a zone, region, area, or location, set use_roi: false.
   Only set use_roi: true when the user explicitly mentions a spatial region.
```

**Result:** Unlocks an entire class of impressive whole-video queries with zero backend changes.

---

### 🥇 Fix 2: Update Example Questions in the UI (30 min, high polish impact)

The current example questions in `intent-pane.tsx` only show ROI-based queries. Adding no-ROI examples would immediately signal to users that the system is more flexible than it looks.

**Current examples:**
```tsx
const EXAMPLE_QUESTIONS = [
  "How many people dwell in the ROI zone for 5 seconds or more?",
  "How many people cross the crosswalk?",
  "How many people enter the store?",
  "How many people exit the store?",
  "What is the average dwell time at the entrance?",
];
```

**Suggested new examples (mix of ROI and no-ROI):**
```tsx
const EXAMPLE_QUESTIONS = [
  // No ROI needed
  "How many people appear in this video?",
  "Count all cars in the video",
  // ROI-based dwell
  "How many people loiter at the entrance for 5+ seconds?",
  "What is the average wait time in the queue?",
  // ROI-based traffic
  "How many people cross the crosswalk?",
  "How many people enter the store?",
  "How many people exit the store?",
  // Object variety
  "How long do trucks idle at the loading dock?",
];
```

---

### 🥉 Fix 3: Show Query Type Indicator in Results (1 hour, moderate impact)

Right now the results pane shows "Metrics + Events" as a static badge. It gives no context about what was actually computed. A small addition — showing the task name and key params — would make results much more readable in a demo screenshot.

**Example addition at the top of ResultsPane:** Show a summary line like:
> `dwell_count · threshold: 5s · 12 tracks analyzed · 2.4s`

This requires passing the `metadata` from the result to the results header. The metadata already exists in the API response (`metadata.task`, `metadata.processing_time_sec`, `metadata.tracks_after_filter`) — it just isn't surfaced in the UI.

---

## The "Green Shirt" Feature — No-ROI Appearance Queries

This idea is technically distinct from the ROI-free counting above. Here's an honest breakdown:

### What it is

> "How many people have a green shirt?" / "Count people wearing red" / "Did anyone in a blue jacket cross the line?"

This requires **color extraction from track crops** — taking the bounding box pixels for each person, converting to HSV color space, and checking if a dominant color matches what the user asked for. No external model needed; it's a few lines of OpenCV.

### Effort vs. Payoff

**Backend (1-2 hours):**
1. Create `backend/app/vision/color.py` — a function `extract_dominant_color(frame_crop) -> str` that converts a crop to HSV and maps to a simple color name ("red", "green", "blue", "black", "white", "yellow")
2. Add `filter_by_appearance` to `filters.py` — for each track, sample a few frame crops, extract color from the torso region (top 40–60% of bbox height), keep tracks where dominant color matches
3. Update `apply_filters` to call it when `filters.appearance` is set
4. Update LLM system prompt with examples and a new rule for appearance queries

**LLM integration (30 min):**
Add examples:
```
Prompt: "How many people have a green shirt?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false,
  "filters": {{"appearance": {{"color": "green", "color_region": "torso"}}}},
  "params": {{"dwell_threshold_seconds": 0}},
  "explanation": "Count people with green torso color — appearance filter, no ROI."}}
```

**The schema already has the slot for this.** `AppearanceFilter` and `ObjectAssociation` are already defined in `schema.py` but are never wired up:

```python
# Already exists in schema.py:
class AppearanceFilter(BaseModel):
    color_region: Literal["torso", "full", "lower", "upper"] = "torso"
    color: str
```

### Important caveat: accuracy

HSV-based color matching is imprecise. It will:
- Misclassify in challenging lighting
- Struggle with patterned clothing
- Fail on dark/black clothing (all look similar in HSV)

For a demo, **this is totally fine** — it works well enough on clear footage with solid-color clothing. Framing matters: present it as "color-based filtering" not "clothing recognition." The impressive part is that the LLM interprets "green shirt" and routes it to a color filter — the actual color accuracy is secondary.

### Verdict: High value for the demo, achievable in 2-3 hours

This is genuinely the most visually distinctive feature you could add before LinkedIn. It:
- Works without drawing ANY ROI (pure whole-video analysis)
- Is visually intuitive — anyone watching the demo instantly understands what's happening
- Has no equivalent in basic analytics tools
- Is easy to film: solid-color shirts on people walking around → easy to verify

---

## What NOT to Add Before Launch

| Feature | Why to Skip |
|---------|------------|
| Object association (phone/table) | 4+ hours, complex, not visible in a short demo clip |
| Vision caching | Performance improvement, not visible as a demo feature |
| Pose detection | Requires new model file, hard to demo without specific footage |
| count_per_interval | Niche, needs specific footage (e.g. traffic light footage) |
| exit_reentry | Edge-case, not visually compelling |
| Timeline charts | Nice but requires a chart library and occupancy data |
| Unit tests | Important but not a demo feature |

---

## Recommended Launch Order

If you want to reach LinkedIn-posting state in a single focused session (3-5 hours total):

1. **[1 hour] Fix 1 — No-ROI LLM examples + rule** → unlocks whole-video queries
2. **[30 min] Fix 2 — Update example questions in UI** → makes the UX feel polished
3. **[2-3 hours] Fix 3 — Appearance filter ("green shirt")** → the standout demo feature
4. **Record demo video showing:**
   - Query with ROI: "How many people loiter for 5 seconds?" (shows ROI drawing → green tracks → result)
   - Query without ROI: "Count all cars in the video" (no drawing required → instant result)
   - Appearance query: "How many people have a green shirt?" (no ROI, color-filtered tracks)

That's a genuinely impressive, diverse, technically credible demo that doesn't take weeks to build.

---

## Summary Table

| Area | Status | Notes |
|------|--------|-------|
| Dwell timing queries (with ROI) | ✅ Fully working | 10+ query types |
| Traffic entry/exit/crossing (with ROI) | ✅ Fully working | All 3 modes |
| Object class variety (80 COCO classes) | ✅ Fully working | LLM picks class automatically |
| Whole-video counting (no ROI) | ⚠️ Backend works, LLM doesn't route there | Fix: add examples to system prompt |
| Color/appearance filtering | ❌ Not implemented | 2-3 hours; highest demo impact |
| Object association (phone at table, etc.) | ❌ Not implemented | High complexity, skip for now |
| Occupancy / density | ❌ Deprioritized | Removed from plan |
| Vision caching | ❌ Deprioritized | Removed from plan |
