"""
LLM planner — converts natural-language prompt to validated analysis plan.

Uses OpenAI GPT-4o-mini with response_format: json_object for structured output.
Spec: PIPELINE-LOGIC.md Section 5.
"""

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from app.pipeline.registry import get_available_tasks, get_task_docs
from app.pipeline.schema import AnalysisPlan

logger = logging.getLogger(__name__)

# System prompt template — injects context and examples
SYSTEM_PROMPT_TEMPLATE = """You are the planning engine for a video analytics application.

Given a user's natural-language question about a video, produce a JSON analysis plan
that selects the correct metric module, vision configuration, filters, and parameters.

## Available Tasks
{task_docs}

## Plan Schema
The plan must be valid JSON with these fields:
- task (string): One of {task_names}. Required.
- object (string): Primary object to detect, e.g. "person". Required.
- use_roi (boolean): Whether to filter by user-drawn ROI polygon. Required.
- params (object): Task-specific parameters. Required. For dwell_count: dwell_threshold_seconds (number). For traffic_count: count_mode ("unique_entries"|"unique_exits"|"unique_crossings"|"first_entry_only").
- roi_instruction (string, optional): When use_roi is true, a short hint for where to draw the ROI, e.g. "Draw an ROI in front of the store." or "Draw an ROI on the crosswalk."
- vision (object, optional): model, detect_classes, confidence_threshold.
- filters (object, optional): roi_mode ("inside"|"enters"|"exits"|"crosses"|"outside"), min_track_frames, appearance ({{"color": string, "color_region": "torso"|"upper"|"lower"|"full"}}).

## Context for This Video
- ROI exists: {roi_exists}
- Video duration: {duration_seconds}s
- Video resolution: {width}x{height}

## Rules
1. Output ONLY valid JSON. No markdown, no code fences, no extra text.
2. task must be one of: {task_names}
3. If the user mentions a zone, area, or region (store, crosswalk, door, entrance, etc.), set use_roi: true and provide roi_instruction.
4. If the user does NOT mention a specific zone or location, set use_roi: false. Do not ask for an ROI when the question is about the whole video.
5. Extract numeric thresholds from the prompt (e.g. "10 seconds" → params.dwell_threshold_seconds: 10).
6. Include an "explanation" field (string) summarizing your reasoning.
7. Set vision.detect_classes to match the object(s) the user asked about. For single-object queries (e.g. cars, people), set detect_classes to [object]. For multi-class queries (e.g. person at table, person on phone), set detect_classes to all needed YOLO classes (e.g. ["person", "dining table"]).
8. If the user mentions a COLOR or clothing attribute, add filters.appearance: {{"color": "<color>", "color_region": "<region>"}}. Use "torso" for shirts/jackets, "lower" for pants/jeans, "upper" for hats, "full" for vehicles. Default to "torso" if ambiguous. Always combine with use_roi: false and dwell_threshold_seconds: 0 unless the user specifies otherwise.

## Examples

Prompt: "How many cars linger in the AOI for more than 5 seconds?"
Plan:
{{"task": "dwell_count", "object": "car", "use_roi": true, "vision": {{"detect_classes": ["car"]}}, "params": {{"dwell_threshold_seconds": 5}}, "roi_instruction": "Draw an ROI around the area of interest (AOI).", "explanation": "User wants to count cars lingering in a specified area for more than 5 seconds."}}

Prompt: "How many people loiter in front of my store for more than 10 seconds?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "params": {{"dwell_threshold_seconds": 10}}, "roi_instruction": "Draw an ROI in front of the store or entrance.", "explanation": "User wants loitering count with 10s threshold in a store-front zone."}}

Prompt: "How long do people wait in the queue?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "params": {{"dwell_threshold_seconds": 0, "report_per_track": true}}, "roi_instruction": "Draw an ROI around the queue area.", "explanation": "Queue wait time = dwell with 0 threshold, report per track."}}

Prompt: "Who stops to look at the display for at least 3 seconds?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "params": {{"dwell_threshold_seconds": 3}}, "roi_instruction": "Draw an ROI around the display or window.", "explanation": "Display engagement = dwell with 3s threshold."}}

Prompt: "How many people cross the crosswalk?"
Plan:
{{"task": "traffic_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "filters": {{"roi_mode": "crosses"}}, "params": {{"count_mode": "unique_crossings"}}, "roi_instruction": "Draw an ROI on the crosswalk.", "explanation": "User wants to count people crossing the crosswalk = traffic_count with crosses mode."}}

Prompt: "How many people enter the store?"
Plan:
{{"task": "traffic_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "filters": {{"roi_mode": "enters"}}, "params": {{"count_mode": "unique_entries"}}, "roi_instruction": "Draw an ROI at the store entrance.", "explanation": "User wants entry count = traffic_count with enters mode."}}

Prompt: "Count cars entering the parking lot"
Plan:
{{"task": "traffic_count", "object": "car", "use_roi": true, "vision": {{"detect_classes": ["car"]}}, "filters": {{"roi_mode": "enters"}}, "params": {{"count_mode": "unique_entries"}}, "roi_instruction": "Draw an ROI at the parking lot entrance.", "explanation": "User wants car entry count = traffic_count."}}

Prompt: "How many people exit the store?"
Plan:
{{"task": "traffic_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "filters": {{"roi_mode": "exits"}}, "params": {{"count_mode": "unique_exits"}}, "roi_instruction": "Draw an ROI at the store exit or doorway.", "explanation": "User wants exit count = traffic_count with exits mode."}}

Prompt: "How many people are in this video?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count all people in the video — no zone mentioned, use_roi: false, threshold 0 to count every appearance."}}

Prompt: "Count all cars in the video"
Plan:
{{"task": "dwell_count", "object": "car", "use_roi": false, "vision": {{"detect_classes": ["car"]}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count all cars visible — no spatial restriction, use_roi: false."}}

Prompt: "How many dogs appear in this footage?"
Plan:
{{"task": "dwell_count", "object": "dog", "use_roi": false, "vision": {{"detect_classes": ["dog"]}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count all dogs in the video — whole-video query, use_roi: false."}}

Prompt: "How many people have a green shirt?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "filters": {{"appearance": {{"color": "green", "color_region": "torso"}}}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count people with green clothing — appearance filter on torso region, no ROI needed."}}

Prompt: "Count people wearing red"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "filters": {{"appearance": {{"color": "red", "color_region": "torso"}}}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count red-clothed people using appearance filter on torso, whole-video query."}}

Prompt: "Did anyone in a blue jacket enter the store?"
Plan:
{{"task": "traffic_count", "object": "person", "use_roi": true, "vision": {{"detect_classes": ["person"]}}, "filters": {{"roi_mode": "enters", "appearance": {{"color": "blue", "color_region": "torso"}}}}, "params": {{"count_mode": "unique_entries"}}, "roi_instruction": "Draw an ROI at the store entrance.", "explanation": "Count blue-jacketed people entering the store — appearance filter combined with ROI entry detection."}}

Prompt: "How many people are wearing yellow?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "filters": {{"appearance": {{"color": "yellow", "color_region": "torso"}}}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count people wearing yellow — appearance filter, no ROI."}}

Prompt: "Count the people in black clothing"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "filters": {{"appearance": {{"color": "black", "color_region": "torso"}}}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count people wearing black — appearance filter on torso region."}}

Prompt: "How many people are wearing blue jeans?"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "filters": {{"appearance": {{"color": "blue", "color_region": "lower"}}}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count people wearing blue jeans — appearance filter on lower body region."}}

Prompt: "Count people with red pants"
Plan:
{{"task": "dwell_count", "object": "person", "use_roi": false, "vision": {{"detect_classes": ["person"]}}, "filters": {{"appearance": {{"color": "red", "color_region": "lower"}}}}, "params": {{"dwell_threshold_seconds": 0}}, "explanation": "Count people with red pants — lower body region for pants/jeans."}}
"""


async def generate_plan(
    prompt: str,
    video_id: str,
    video_meta: dict,
    roi_exists: bool,
) -> AnalysisPlan:
    """
    Convert a natural-language prompt to a validated analysis plan.

    Args:
        prompt: User's question (e.g. "How many people loiter for 10 seconds?")
        video_id: Video identifier (for logging).
        video_meta: Dict with fps, duration, width, height from extract_metadata.
        roi_exists: Whether an ROI polygon is saved for this video.

    Returns:
        Validated AnalysisPlan.

    Raises:
        ValueError: If LLM returns invalid JSON or validation fails.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is not set. "
            "Set it to use the LLM planner."
        )

    task_names = ", ".join(get_available_tasks())
    task_docs = get_task_docs()

    duration = video_meta.get("duration", 0)
    width = video_meta.get("width", 0)
    height = video_meta.get("height", 0)

    system_content = SYSTEM_PROMPT_TEMPLATE.format(
        task_docs=task_docs,
        task_names=task_names,
        roi_exists=roi_exists,
        duration_seconds=round(duration, 1),
        width=int(width),
        height=int(height),
    )

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": f'User prompt: "{prompt}"'},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
    except Exception as e:
        logger.exception("OpenAI API call failed")
        raise ValueError(f"LLM call failed: {e}") from e

    content = response.choices[0].message.content

    try:
        plan_dict: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON: %s", content[:500])
        raise ValueError(f"LLM returned invalid JSON: {e}") from e

    # Validate with Pydantic
    try:
        plan = AnalysisPlan.model_validate(plan_dict)
    except Exception as e:
        logger.error("Plan validation failed: %s", plan_dict)
        raise ValueError(f"Plan validation failed: {e}") from e

    # Ensure task is implemented
    if plan.task.value not in get_available_tasks():
        raise ValueError(
            f"LLM produced task '{plan.task.value}' which is not implemented. "
            f"Available: {get_available_tasks()}"
        )

    logger.info(
        f"Planner: prompt -> task={plan.task.value}, use_roi={plan.use_roi}, "
        f"params={plan.params}"
    )
    return plan
