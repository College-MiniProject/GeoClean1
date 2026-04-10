# GeoClean AI Verification System
## Setup & Run Instructions

### Overview
This module adds intelligent garbage detection and anti-cheating validation to the GeoClean backend. It uses:
- **MobileNetV2 via ONNX Runtime** — Pre-trained image classifier (1000 ImageNet categories)
- **OpenCV + SSIM** — Before/after image comparison to detect fake cleanups
- **Rule-based anti-cheating** — Location cooldown, time gap, and daily limits

---

### Prerequisites
- Python 3.9+
- pip

### Installation

```bash
# Navigate to the backend directory
cd backend

# (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# Install all dependencies
pip install -r requirements.txt
```

> **Note:** ONNX Runtime will download the MobileNetV2 weights (~14MB) on first run.
> This happens automatically and is cached in the `models/` directory.

### Running the Server

```bash
python app.py
```

The server starts on `http://localhost:5050` (or `0.0.0.0:5050`).

### Running Tests

In a **separate terminal** (while the server is running):

```bash
python test_verification.py
```

---

### API Endpoints

#### 1. `POST /upload-before`
Upload a "before cleaning" image with GPS location.

**Request Body (JSON):**
```json
{
    "image": "<base64 encoded image>",
    "latitude": 17.3850,
    "longitude": 78.4867,
    "user_id": "user@email.com"
}
```

**Response:**
```json
{
    "success": true,
    "session_id": "abc123def456",
    "message": "Before image uploaded successfully...",
    "timestamp": "2026-04-10T22:30:00"
}
```

#### 2. `POST /upload-after`
Upload an "after cleaning" image linked to a session.

**Request Body (JSON):**
```json
{
    "image": "<base64 encoded image>",
    "session_id": "abc123def456"
}
```

**Response:**
```json
{
    "success": true,
    "session_id": "abc123def456",
    "message": "After image uploaded successfully..."
}
```

#### 3. `POST /validate-cleaning`
Run the full AI + comparison + anti-cheating pipeline.

**Request Body (JSON):**
```json
{
    "session_id": "abc123def456"
}
```

**Response (Accepted):**
```json
{
    "success": true,
    "status": "accepted",
    "ai_prediction": {
        "is_garbage": true,
        "detected_labels": [...],
        "confidence_score": 0.45
    },
    "image_comparison": {
        "ssim_score": 0.62,
        "pixel_difference": 0.18,
        "status": "accepted"
    },
    "validation_rules": {
        "all_passed": true,
        "checks": {...}
    }
}
```

**Response (Rejected):**
```json
{
    "success": false,
    "status": "rejected",
    "rejection_reasons": [
        "Images are nearly identical...",
        "Daily reward limit reached..."
    ]
}
```

#### 4. `GET /session-status/<session_id>`
Check the current state of a verification session.

---

### Project Structure

```
backend/
├── app.py                          # Main Flask app (registers verification blueprint)
├── requirements.txt                # All Python dependencies
├── verification_routes.py          # Flask blueprint with API endpoints
├── verification/                   # AI verification module
│   ├── __init__.py
│   ├── image_prediction.py         # MobileNetV2 image classification
│   ├── garbage_detection.py        # Keyword-based garbage detection
│   ├── image_comparison.py         # OpenCV SSIM + pixel diff comparison
│   └── validation_rules.py         # Anti-cheating rules
├── test_verification.py            # Test script
└── uploads/
    └── verification/               # Temporary image storage
```

### Anti-Cheating Measures

| Check | What It Does | Threshold |
|-------|-------------|-----------|
| **AI Garbage Detection** | Classifies before-image using MobileNetV2 | Keywords match |
| **SSIM Comparison** | Structural similarity between before/after | > 0.90 = rejected |
| **Pixel Difference** | Mean absolute pixel change | < 0.05 = rejected |
| **Location Cooldown** | Same spot can't be rewarded within 24h | 100m radius |
| **Minimum Time Gap** | Before/after uploads must be 5+ min apart | 5 minutes |
| **Daily Reward Limit** | Max 5 rewards per user per day | 5/day |
