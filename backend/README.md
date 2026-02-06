# Backend - Video Upload & Metadata API

## Setup and Run

### 1. Create virtual environment (if not already done)
```bash
cd backend
python -m venv venv
```

### 2. Activate virtual environment
```bash
# On Mac/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Install/Update dependencies (includes OpenCV)
```bash
pip install -r requirements.txt
```

**Note:** OpenCV installation may take 1-2 minutes

### 4. Run the backend server
```bash
uvicorn app.main:app --reload --port 8000
```

The backend will be available at: `http://localhost:8000`

## Test the Complete Flow

1. **Start backend** (Terminal 1):
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn app.main:app --reload --port 8000
   ```

2. **Frontend already running** (Terminal 2):
   ```bash
   pnpm dev  # Should already be running on localhost:3000
   ```

3. **Upload a video**:
   - Go to http://localhost:3000
   - Click "Choose file"
   - Select a video
   - Watch the console for:
     ```
     ✅ Upload successful! {...}
     📊 Metadata extracted: {fps: 60, frame_count: 7200, duration: 120}
     ```
   - Video should play in the Evidence pane!

## API Endpoints

- `GET /` - Health check
- `POST /api/upload` - Upload video file
- `GET /api/video/{video_id}/metadata` - Get video metadata (fps, frames, duration)
- `GET /api/video/{video_id}` - Stream/download video file

## What's Working Now

✅ Video upload from frontend
✅ Video saved to backend
✅ OpenCV extracts metadata (fps, frame count, duration)
✅ Video plays in frontend
✅ Real metadata displayed in UI

## Folder Structure

```
backend/
├── app/
│   ├── __init__.py           # Package marker
│   ├── main.py               # FastAPI app with all endpoints
│   └── core/
│       ├── __init__.py       # Package marker
│       └── decode.py         # OpenCV metadata extraction
├── uploads/                  # Uploaded videos stored here
├── requirements.txt          # Python dependencies (includes OpenCV)
└── README.md                # This file
```
