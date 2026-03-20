# Zapier for Computer Vision — Product Planning Doc

---

## The Core Idea

Analytics Mate already does something powerful: you describe what you want to track in plain English, and the system figures out how to detect it. But right now it stops there — you get back a number and a video. Nothing *happens* as a result of what it finds.

This feature closes that loop. Instead of just asking "how many people are wearing green jackets?", you define a rule: **when** people wearing green jackets exceed a threshold, **do something** — call an API, send a text, fire a webhook.

That's the full analogy to Zapier. Zapier connects triggers (something happened in app A) to actions (do something in app B). This connects CV detection events (something happened on camera) to real-world actions (notify someone, call a service, automate a response).

---

## Why This Doesn't Exist Yet

Enterprise camera platforms (Milestone, Genetec, Avigilon, Verkada) have rule-based alerting. But:

- Conditions are fixed and pre-defined — you pick from a list of supported detection types, you don't describe them
- Actions are walled inside their ecosystem — alerts, notifications to their own app, maybe an email
- Not programmable — there's no "bring your own webhook" concept, no developer-first model
- Expensive and opaque — you can't inspect or compose the logic

Newer AI camera companies (Spot AI, Rhombus) are smarter but still ship rigid, curated condition types. The gap is: **natural language condition definition + arbitrary user-defined actions** as a composable system. Nobody has built that cleanly.

---

## What a Rule Looks Like

A rule has three parts:

```
WHEN  [detection condition]
AND   [threshold / context]
THEN  [action]
```

### Examples

| When | And | Then |
|---|---|---|
| People wearing green jackets are detected | Count > 0 | POST to `https://my-api.com/capture-photo` |
| People are present in the entrance zone | Count > 5 for 10+ seconds | Send SMS: "Alert — line forming at entrance" |
| People loitering near the loading dock | Any detection | POST to internal security webhook |
| A vehicle is parked in the fire lane ROI | Duration > 30 seconds | Send SMS to manager |
| Foot traffic in store exceeds threshold | Count > 20 in last 5 minutes | Trigger capacity alert API |

The condition is natural language. The system translates it into a detection plan (the same LLM planner that already exists). The threshold is a structured config. The action is user-defined — a URL, a phone number, an email address.

---

## System Architecture

### Current State
```
User prompt → LLM planner → AnalysisPlan JSON → YOLO+ByteTrack → Events + Metrics → Annotated video
```

### With Rules Engine
```
Saved Rule
  └─ Condition (natural language) → pre-compiled AnalysisPlan
  └─ Threshold config
  └─ Action config (webhook / SMS / email)

On Analysis Run:
  → Pipeline fires events as usual
  → Rules engine checks: do any fired events match a saved rule's conditions?
  → If threshold is crossed → execute action
```

### Components to Build

**1. Rule Storage**
JSON file (same pattern as ROI storage). Each rule has:
- `id` — UUID
- `name` — human readable label
- `condition` — natural language string
- `compiled_plan` — the AnalysisPlan JSON the LLM produced from the condition (cached so it doesn't re-call the LLM on every run)
- `threshold` — `{ type: "count" | "duration" | "any", value: number, window_seconds?: number }`
- `action` — `{ type: "webhook" | "sms" | "email", ...config }`
- `enabled` — bool
- `created_at`

**2. Rules Builder UI**
A dedicated Rules page in the frontend. Key interactions:
- List of saved rules with enable/disable toggles
- "New Rule" flow — a multi-step form:
  - Step 1: Name your rule + describe the condition in natural language
  - Step 2: Set the threshold (count, duration, any detection)
  - Step 3: Configure the action (pick type, fill in endpoint/number/address)
  - Step 4: Review compiled plan — shows the JSON the LLM produced so the user can verify the condition was understood correctly
- Edit and delete

**3. Action Runner (Backend)**
A Python module that, given a fired event and a matched rule, executes the configured action:
- `webhook` — HTTP POST with event payload (JSON: what was detected, when, count, video_id)
- `sms` — Twilio API call (requires Twilio credentials in `.env`)
- `email` — SMTP or SendGrid (optional, lower priority)

**4. Rule Matching (Backend)**
After a pipeline run completes, before returning the response:
- Load all enabled rules
- For each rule, check if its compiled plan's task/filters match the current run's plan
- If matched, check the threshold against the returned events
- If threshold crossed, call the action runner

---

## Data Model

### Rule Object
```json
{
  "id": "uuid",
  "name": "Alert: Green Jacket Spotted",
  "condition": "people wearing green jackets",
  "compiled_plan": {
    "task": "dwell_count",
    "object": "person",
    "filters": { "appearance": { "color": "green", "color_region": "torso" } },
    ...
  },
  "threshold": {
    "type": "count",
    "value": 1
  },
  "action": {
    "type": "sms",
    "to": "+15551234567",
    "message_template": "Alert: {{count}} person(s) wearing green jackets detected at {{timestamp}}"
  },
  "enabled": true,
  "created_at": "2026-03-19T00:00:00Z"
}
```

### Action Payload (sent to webhooks)
```json
{
  "rule_id": "uuid",
  "rule_name": "Alert: Green Jacket Spotted",
  "video_id": "...",
  "triggered_at": "2026-03-19T12:34:56Z",
  "event_count": 3,
  "events": [
    { "track_id": 7, "start_time": 4.2, "end_time": 18.1, "duration_seconds": 13.9 }
  ]
}
```

---

## UI Mockup (Described)

### Rules List Page
```
[ + New Rule ]

┌─────────────────────────────────────────────────────────────────┐
│  ● Alert: Green Jacket Spotted                       [Edit] [×] │
│  Condition: people wearing green jackets                        │
│  Threshold: count ≥ 1                                           │
│  Action: SMS → +1 555 123 4567                                  │
│  Toggle: [ON ●──]                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ● Line Alert                                        [Edit] [×] │
│  Condition: people queuing in the entrance area                 │
│  Threshold: count ≥ 5                                           │
│  Action: Webhook → https://hooks.internal.co/alert             │
│  Toggle: [ON ●──]                                               │
└─────────────────────────────────────────────────────────────────┘
```

### New Rule Form (Step 2 of 4 — Threshold)
```
Step 2: When should this rule fire?

  ( ) Any detection — fire immediately when condition is met
  (●) Count threshold — fire when detected count reaches ___5___
  ( ) Duration threshold — fire when someone is present for _____ seconds

  [ Back ]  [ Next: Configure Action → ]
```

---

## Phased Build Plan

### Phase 1 — Core Rules Engine (Batch Video)
Works with the existing batch video flow. When you run analysis on a video, the system checks if any enabled rules match the results and fires their actions.
- Rule CRUD (create, read, update, delete) — backend + storage
- Action runner: webhook + SMS
- Rule matching after pipeline run
- Rules Builder UI

### Phase 2 — Rules Attached to Videos
Associate specific rules with specific video sources (or all videos). When a video is analyzed, only run the rules attached to it. This matters more once live streams exist.

### Phase 3 — Live Camera Streams
The biggest architectural step. Instead of processing uploaded files:
- Connect to an RTSP stream URL
- Process frames in a rolling window using the same YOLO+ByteTrack stack
- Evaluate rules continuously against the rolling window
- Fire actions in real time

This is what turns the system from a video analytics tool into a genuine ambient intelligence layer — cameras watching, rules evaluating, actions firing, all without a human in the loop.

---

## Why This Matters

The current product answers questions retroactively — you upload a video and ask "what happened?" This feature makes it prospective — you define what you care about ahead of time and the system tells you when it happens.

That's the difference between a reporting tool and an operational system. The reporting tool is useful. The operational system is the business.

---

*Created: March 2026*
