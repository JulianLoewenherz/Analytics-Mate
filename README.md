# Analytics Mate

An AI-assisted workspace for **asking questions about video** in plain English and getting **traceable evidence** back (events, timestamps, annotated video) — not a black-box dashboard.

At a glance: **Intent → Plan (JSON) → Run → Evidence → Iterate**.

## What it can do

- **Dwell / loitering (timing)**: “How many people loiter for 5+ seconds?”, “Average wait time in the queue?”
- **Traffic / counting (transitions)**: “How many people enter / exit?”, “How many people cross the crosswalk?”
- **Whole-video queries (no ROI)**: “How many people appear in this video?”, “Count all cars”
- **Appearance filtering (color)**: “How many people have a green shirt?”, “blue jeans” (HSV-based color filter on track crops)
- **Object flexibility**: works across **80 COCO classes** supported by YOLO (person, car, bus, dog, …)

## How it works

1. **LLM planner** converts your prompt into a **schema-validated JSON plan** (no code execution).
2. **Vision** runs YOLO detection + ByteTrack-style tracking to produce per-object tracks.
3. **Filters** apply ROI / quality / appearance constraints.
4. **Metrics** compute results (`dwell_count`, `traffic_count`) and emit **events + aggregates**.
5. **Visualizer** renders an annotated MP4 (red/yellow/green state overlays).

## Quickstart (local)

### Backend (FastAPI)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# set env var (recommended) or copy .env.example -> .env
export OPENAI_API_KEY="..."

uvicorn app.main:app --reload
```

### Frontend (Next.js)

```bash
npm install
npm run dev
```

Open the app, upload a video, optionally draw an ROI, ask a question, and run.

## Example prompts

- “How many people loiter at the entrance for 5+ seconds?”
- “How many people cross the crosswalk?”
- “Count all cars in the video”
- “How many people have a green shirt?”
- “How many people are wearing blue jeans?”

## Safety / design notes

- The LLM only produces a **structured JSON plan**; execution is limited to **registered metric modules**.
- Keep secrets out of the repo. `.env` is ignored — use `.env.example` as a template.

See [`PLANNING.md`](./PLANNING.md) for deeper architecture notes and roadmap.
