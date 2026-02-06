# Analytics Mate

**Cursor for video analytics** — an AI-assisted workspace where you ask questions about video in plain language and iteratively build, inspect, and refine the logic that answers them, backed by visual evidence.

Not “upload video → black box → charts.” Instead: **ask → see the plan → run step-by-step → edit parameters → re-run** and trace every result back to the video.

### MVP in one sentence

Upload a video, ask something like *“How many people dwell outside my store?”, “How many people are bicycling?”, “How many dogs are in this park?”, or “How many people cross per walk signal on average?”*, get an **editable analysis plan** (e.g. objects of interest, ROI, time windows, thresholds), draw your region of interest, run the pipeline, and see annotated video + event list + counts—then tweak and re-run.

### Tech (MVP)

- **Backend:** Python, YOLOv8/YOLOv11 (object + person detection), ByteTrack (tracking), OpenCV, NumPy  
- **Frontend:** Streamlit (fastest path) or Next.js + FastAPI  
- **AI:** LLM outputs a **structured plan (JSON)** only; no arbitrary code execution. Plan maps to fixed metric modules (e.g. `dwell_count`, `traffic_count`).

### Core loop

**Intent** (natural language) → **Plan** (editable, human-readable steps) → **Evidence** (boxes, tracks, events, timeline) → **Tweak** (sliders, ROI, filters) → **Re-run**.

See **[PLANNING.md](./PLANNING.md)** for the full MVP feature list, tech stack, logic structure, build order, and plan format.
