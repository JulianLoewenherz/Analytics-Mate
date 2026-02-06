# ROI Drawing Implementation Plan (MVP)

**Goal:** Enable users to draw a polygon on a video frame and save those points.

**Use Case Example:** Draw a polygon around a bus entrance so you can later count people passing through.

---

## What We're Building (Simple Version)

### Core Concept
- An ROI is just a list of points: `[{x: 100, y: 200}, {x: 300, y: 250}, ...]`
- User clicks on a frame to add points
- Points connect to form a polygon
- We save these points with the video ID
- We can load and display them later

### User Flow
1. User loads a video
2. Clicks "Draw ROI" button  
3. A canvas shows the current frame
4. User clicks to add polygon points
5. Double-click to finish
6. Click "Save" → points sent to backend
7. ROI shows as overlay on video

---

## Files to Create

### 1. **Frontend: `components/workspace/roi-canvas.tsx`**
**Purpose:** Canvas component for drawing polygons

**Core State:**
```typescript
const [points, setPoints] = useState<Point[]>([]);        // Polygon vertices
const [isComplete, setIsComplete] = useState(false);      // Is polygon closed?
const [hoveredPoint, setHoveredPoint] = useState<number | null>(null);
```

**Key Functions:**
- `handleCanvasClick()` - Add point on click
- `handleDoubleClick()` - Complete polygon
- `drawPolygon()` - Render points and lines on canvas
- `isNearStartPoint()` - Check if click is near first point (auto-close)
- `onSave()` - Send polygon to parent component

**Visual Elements:**
- Background: video frame (as image)
- Points: small circles at each vertex
- Lines: connecting consecutive points
- Preview line: from last point to mouse cursor (while drawing)
- Fill: semi-transparent overlay when complete

---

### 2. **Backend: `backend/app/storage/roi_storage.json`**
**Purpose:** Simple file-based storage for ROIs (MVP approach)

**Structure:**
```json
{
  "video_id_1": {
    "polygon": [
      {"x": 450, "y": 200},
      {"x": 650, "y": 200},
      {"x": 650, "y": 500},
      {"x": 450, "y": 500}
    ],
    "name": "bus_entrance",
    "created_at": "2026-02-06T10:30:00Z"
  }
}
```

**Note:** Start with JSON file - simplest approach. Can move to database later if needed.

---

## Files to Modify

### 1. **`components/workspace/evidence-pane.tsx`**

**Changes:**
- Add "Draw ROI" button (appears when video is loaded)
- Add state: `const [showROICanvas, setShowROICanvas] = useState(false)`
- Add state: `const [savedROI, setSavedROI] = useState<Polygon | null>(null)`
- Add handler to capture current video frame as image
- Conditionally render `<ROICanvas>` component
- Display saved ROI as SVG overlay on video

**New UI Flow:**
```
[Video Player]
  └─ [Draw ROI Button]
       └─ onClick → pause video, capture frame
            └─ Show <ROICanvas> with frame
                 └─ User draws polygon
                      └─ onSave → POST to backend
                           └─ Close canvas, show ROI overlay on video
```

---

### 2. **`backend/app/main.py`**

**Add 3 New Endpoints:**

#### Endpoint 1: Get a specific frame as image
```python
@app.get("/api/video/{video_id}/frame/{frame_number}")
async def get_frame(video_id: str, frame_number: int):
    """
    Extract frame N from video and return as JPEG
    
    Steps:
    1. Open video with cv2.VideoCapture
    2. Seek to frame number: cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    3. Read frame: ret, frame = cap.read()
    4. Encode as JPEG
    5. Return with media_type="image/jpeg"
    """
```

#### Endpoint 2: Save ROI
```python
@app.post("/api/video/{video_id}/roi")
async def save_roi(video_id: str, roi_data: dict):
    """
    Save ROI polygon for a video
    
    Steps:
    1. Validate ROI has at least 3 points
    2. Load existing ROIs from roi_storage.json
    3. Add/update ROI for this video_id
    4. Write back to file
    5. Return success
    
    Expects JSON: {"polygon": [{"x": 100, "y": 200}, ...]}
    """
```

#### Endpoint 3: Get saved ROI
```python
@app.get("/api/video/{video_id}/roi")
async def get_roi(video_id: str):
    """
    Retrieve saved ROI for a video
    
    Steps:
    1. Load roi_storage.json
    2. Find ROI for video_id
    3. Return ROI or 404 if not found
    """
```

---

## Implementation Steps (In Order)

### **Step 1: Get a Frame from Video** (20 min)
1. ✅ OpenCV already in requirements.txt
2. Add endpoint: `GET /api/video/{id}/frame/{frame_num}`
3. Use OpenCV to extract frame and return as JPEG
4. Test in browser: Should see a single frame image

### **Step 2: Draw on Canvas** (1-2 hours)
1. Create `components/workspace/roi-canvas.tsx`
2. Load frame image as canvas background
3. Handle click to add points
4. Draw circles at each point
5. Draw lines connecting points
6. Add double-click to finish polygon
7. Test: Click around and see polygon form

### **Step 3: Save Points to Backend** (45 min)
1. Create `backend/app/storage/` folder
2. Create empty `roi_storage.json` file: `{}`
3. Add endpoint: `POST /api/video/{id}/roi` 
4. Read/write JSON file to store polygon
5. Add endpoint: `GET /api/video/{id}/roi`
6. Frontend: Send polygon to backend on save
7. Test: Save → Check roi_storage.json has your points

### **Step 4: Display Saved ROI** (30 min)
1. Load ROI when video loads
2. Show polygon as SVG overlay on video
3. Make it semi-transparent (so video visible underneath)
4. Test: Refresh page → ROI should reappear

---

## Testing Checklist

- [ ] Backend returns frame 0 as JPEG image
- [ ] Can click on canvas to add points
- [ ] Points show as circles and connect with lines
- [ ] Double-click completes the polygon
- [ ] Can save polygon to backend
- [ ] `roi_storage.json` contains the saved points
- [ ] After page refresh, ROI loads and displays
- [ ] ROI overlay visible on video

---

## What We're NOT Doing (Keeping it Simple)

❌ **Multiple ROIs** - Just 1 ROI per video for now
❌ **Editing ROI** - To change it, just delete and redraw
❌ **Point-in-polygon logic** - Not needed until detection filtering (Step 5)
❌ **Coordinate normalization** - Using raw pixel coordinates for MVP
❌ **Curved paths** - Straight lines between points only
❌ **Undo/redo** - Clear button to start over

---

## Key Technical Decisions

### Canvas vs SVG for Drawing?
**Choice: HTML Canvas**
- Better for real-time drawing interactions
- Easier to capture frame as background
- SVG can be used for display overlay later

### Storage: JSON file vs Database?
**Choice: JSON file (MVP)**
- Simpler to set up
- No database dependencies
- Easy to inspect/debug
- Can migrate to DB later if needed

### Coordinates: Pixel vs Normalized?
**Choice: Pixel coordinates (simplest)**
- Store exact x, y pixel values from canvas
- ROI is tied to specific video resolution
- Can add normalization later if needed

---

## What Comes After ROI?

Once drawing + saving works, you'll move to **Step 2: Person Detection**

At that point you'll need:
- YOLO to detect people in frames
- Logic to check if detections are inside the ROI polygon
- That's when you'll add a `point_in_polygon()` function

**But you don't need that now!** Just get the drawing working first.

---

## Visual Reference

### What User Sees:

```
┌─────────────────────────────────┐
│  [Draw ROI] button              │
├─────────────────────────────────┤
│                                 │
│     VIDEO FRAME                 │
│                                 │
│      ●────────●  ← polygon      │
│      │        │     points      │
│      │  ROI   │                 │
│      ●────────●                 │
│                                 │
│   [Clear] [Save]                │
└─────────────────────────────────┘
```

### After Saving:

```
┌─────────────────────────────────┐
│  [Edit ROI]  [Hide ROI]         │
├─────────────────────────────────┤
│                                 │
│     VIDEO PLAYING               │
│                                 │
│      ┌────────┐                 │
│      │░░░░░░░░│  ← semi-        │
│      │░░ROI░░░│     transparent  │
│      └────────┘     overlay     │
│                                 │
└─────────────────────────────────┘
```

---

## Quick Start Summary

**All you're building:**
1. Backend endpoint to get a video frame as image
2. Canvas component where user clicks to draw polygon
3. Backend endpoints to save/load the polygon points
4. Display the saved polygon on the video

**Time estimate:** 2-3 hours for MVP

**Key principle:** Just get points drawn and saved. Don't worry about complex geometry or validation yet!
