# Backend - Video Upload API

## Setup and Run

### 1. Create virtual environment
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

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the backend server
```bash
uvicorn app.main:app --reload --port 8000
```

The backend will be available at: `http://localhost:8000`

## Test the Backend

Visit `http://localhost:8000` in your browser - you should see:
```json
{"status": "ok", "message": "Video Analytics Backend is running"}
```

## API Endpoints

- `GET /` - Health check
- `POST /api/upload` - Upload video file

## Folder Structure

```
backend/
├── app/
│   ├── __init__.py       # Package marker
│   └── main.py           # FastAPI app with upload endpoint
├── uploads/              # Uploaded videos stored here
├── requirements.txt      # Python dependencies
└── README.md            # This file
```
