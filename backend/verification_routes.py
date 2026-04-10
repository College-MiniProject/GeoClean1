"""
verification_routes.py — Flask Blueprint for GeoClean AI Verification
=====================================================================
Provides three API endpoints:

  POST /upload-before   → Accept a "before cleaning" image + location + user_id
  POST /upload-after    → Accept an "after cleaning" image + link to before session
  POST /validate-cleaning → Run AI prediction + image comparison + anti-cheating rules

All responses are JSON with clear status, reasons, and data fields.
Sessions are stored in-memory (dict) for simplicity — suitable for a
single-server college project deployment.
"""

import os
import uuid
import base64
from datetime import datetime
from flask import Blueprint, request, jsonify

# Import our verification modules
from verification.image_prediction import predict_image
from verification.garbage_detection import detect_garbage
from verification.image_comparison import compare_images
from verification.validation_rules import run_all_validations

# ---------------------------------------------------------------
# Flask Blueprint setup
# ---------------------------------------------------------------
verification_bp = Blueprint("verification", __name__)

# ---------------------------------------------------------------
# In-memory session store for before/after image pairs
# Key: session_id (str)
# Value: dict with image data, timestamps, location, user info
#
# NOTE: In production, use Redis or a database. This is fine for
# a college project running on a single server.
# ---------------------------------------------------------------
_sessions = {}

# Directory to temporarily store uploaded images
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "verification")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------
# Simulated "recent rewards" store for location cooldown checking
# In production, this would query the database.
# ---------------------------------------------------------------
_recent_rewards = []

# ---------------------------------------------------------------
# Track daily reward counts per user (resets conceptually each day)
# ---------------------------------------------------------------
_daily_counts = {}  # { "user@email.com": { "date": "2026-04-10", "count": 3 } }


def _save_image_to_disk(base64_str: str, prefix: str = "img") -> str:
    """
    Save a base64-encoded image to disk and return the filepath.
    """
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,")[1]

    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.png"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(base64.b64decode(base64_str))

    return filepath


def _get_daily_count(user_id: str) -> int:
    """Get how many rewards a user has claimed today."""
    today = datetime.now().strftime("%Y-%m-%d")
    entry = _daily_counts.get(user_id, {})
    if entry.get("date") == today:
        return entry.get("count", 0)
    return 0


def _increment_daily_count(user_id: str):
    """Increment a user's daily reward count."""
    today = datetime.now().strftime("%Y-%m-%d")
    entry = _daily_counts.get(user_id, {})
    if entry.get("date") == today:
        _daily_counts[user_id]["count"] = entry.get("count", 0) + 1
    else:
        _daily_counts[user_id] = {"date": today, "count": 1}


# ===================================================================
# ENDPOINT 1: POST /upload-before
# ===================================================================
@verification_bp.route("/upload-before", methods=["POST"])
def upload_before():
    """
    Accept a "before cleaning" image along with GPS location and user ID.
    Creates a verification session and returns a session_id for linking
    the subsequent after-image upload.

    Expected JSON body:
    {
        "image": "<base64 encoded image>",
        "latitude": 17.3850,
        "longitude": 78.4867,
        "user_id": "user@email.com"
    }
    """
    data = request.json
    if not data:
        return jsonify({"success": False, "reason": "Request body is required."}), 400

    # --- Extract and validate fields ---
    image_b64 = data.get("image")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    user_id = data.get("user_id")

    if not image_b64:
        return jsonify({"success": False, "reason": "Image (base64) is required."}), 400
    if not user_id:
        return jsonify({"success": False, "reason": "User ID is required."}), 400

    # --- Save image to disk ---
    try:
        before_path = _save_image_to_disk(image_b64, prefix="before")
    except Exception as e:
        return jsonify({"success": False, "reason": f"Failed to save image: {str(e)}"}), 400

    # --- Create a verification session ---
    session_id = uuid.uuid4().hex
    _sessions[session_id] = {
        "user_id": user_id,
        "before_image_path": before_path,
        "before_image_b64": image_b64,
        "before_timestamp": datetime.now(),
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
        "after_image_path": None,
        "after_image_b64": None,
        "after_timestamp": None,
        "status": "awaiting_after",
    }

    return jsonify({
        "success": True,
        "session_id": session_id,
        "message": "Before image uploaded successfully. Now upload the after image.",
        "timestamp": _sessions[session_id]["before_timestamp"].isoformat(),
    }), 201


# ===================================================================
# ENDPOINT 2: POST /upload-after
# ===================================================================
@verification_bp.route("/upload-after", methods=["POST"])
def upload_after():
    """
    Accept an "after cleaning" image and link it to an existing session.

    Expected JSON body:
    {
        "image": "<base64 encoded image>",
        "session_id": "<from upload-before response>"
    }
    """
    data = request.json
    if not data:
        return jsonify({"success": False, "reason": "Request body is required."}), 400

    image_b64 = data.get("image")
    session_id = data.get("session_id")

    if not image_b64:
        return jsonify({"success": False, "reason": "Image (base64) is required."}), 400
    if not session_id:
        return jsonify({"success": False, "reason": "Session ID is required."}), 400

    # --- Validate the session exists ---
    session = _sessions.get(session_id)
    if not session:
        return jsonify({"success": False, "reason": "Invalid session ID. Upload a before image first."}), 404
    if session["status"] != "awaiting_after":
        return jsonify({"success": False, "reason": f"Session is in '{session['status']}' state. Cannot upload after image."}), 400

    # --- Save after image to disk ---
    try:
        after_path = _save_image_to_disk(image_b64, prefix="after")
    except Exception as e:
        return jsonify({"success": False, "reason": f"Failed to save image: {str(e)}"}), 400

    # --- Update session ---
    session["after_image_path"] = after_path
    session["after_image_b64"] = image_b64
    session["after_timestamp"] = datetime.now()
    session["status"] = "ready_for_validation"

    return jsonify({
        "success": True,
        "session_id": session_id,
        "message": "After image uploaded successfully. You can now validate the cleaning.",
        "timestamp": session["after_timestamp"].isoformat(),
    }), 201


# ===================================================================
# ENDPOINT 3: POST /validate-cleaning
# ===================================================================
@verification_bp.route("/validate-cleaning", methods=["POST"])
def validate_cleaning():
    """
    Run the full validation pipeline on a before/after image session:
      1. AI Prediction — classify the 'before' image with MobileNetV2
      2. Garbage Detection — check if trash-related objects are detected
      3. Image Comparison — compare before/after images (SSIM + pixel diff)
      4. Anti-Cheating Rules — location cooldown, time gap, daily limit

    Expected JSON body:
    {
        "session_id": "<from upload-before response>"
    }

    Returns a comprehensive validation result with pass/fail status
    and detailed reasoning for each check.
    """
    data = request.json
    if not data:
        return jsonify({"success": False, "reason": "Request body is required."}), 400

    session_id = data.get("session_id")
    if not session_id:
        return jsonify({"success": False, "reason": "Session ID is required."}), 400

    # --- Validate session state ---
    session = _sessions.get(session_id)
    if not session:
        return jsonify({"success": False, "reason": "Invalid session ID."}), 404
    if session["status"] != "ready_for_validation":
        return jsonify({
            "success": False,
            "reason": f"Session is in '{session['status']}' state. Both images must be uploaded first.",
        }), 400

    # Mark session as processing
    session["status"] = "validating"

    # ------------------------------------------------------------------
    # STEP 1: AI Image Prediction on the "before" image
    # ------------------------------------------------------------------
    try:
        predictions = predict_image(session["before_image_path"], top_n=10)
    except Exception as e:
        predictions = []
        print(f"[GeoClean AI] Prediction error: {e}")

    # ------------------------------------------------------------------
    # STEP 2: Garbage Detection from predictions
    # ------------------------------------------------------------------
    garbage_result = detect_garbage(predictions)

    # ------------------------------------------------------------------
    # STEP 3: Image Comparison (before vs after)
    # ------------------------------------------------------------------
    comparison_result = compare_images(
        session["before_image_path"],
        session["after_image_path"],
    )

    # ------------------------------------------------------------------
    # STEP 4: Anti-Cheating Rule Validation
    # ------------------------------------------------------------------
    user_id = session["user_id"]
    daily_count = _get_daily_count(user_id)

    validation_result = run_all_validations(
        latitude=session["latitude"],
        longitude=session["longitude"],
        before_timestamp=session["before_timestamp"],
        after_timestamp=session["after_timestamp"],
        user_id=user_id,
        today_reward_count=daily_count,
        recent_rewards=_recent_rewards,
    )

    # ------------------------------------------------------------------
    # FINAL DECISION: Combine all results
    # ------------------------------------------------------------------
    rejection_reasons = []

    # Check garbage detection (warning only — not a hard rejection)
    garbage_warning = None
    if not garbage_result["is_garbage"]:
        garbage_warning = (
            "AI could not confidently detect garbage in the 'before' image. "
            "The image may still be valid — manual review recommended."
        )

    # Check image comparison
    if comparison_result["status"] == "rejected":
        rejection_reasons.append(comparison_result["reason"])
    elif comparison_result["status"] == "suspicious":
        rejection_reasons.append(comparison_result["reason"])

    # Check anti-cheating rules
    if not validation_result["all_passed"]:
        rejection_reasons.extend(validation_result["failed_reasons"])

    # Determine overall result
    if len(rejection_reasons) > 0:
        overall_status = "rejected"
        session["status"] = "rejected"
    else:
        overall_status = "accepted"
        session["status"] = "accepted"

        # Record the reward for location cooldown tracking
        _recent_rewards.append({
            "latitude": session["latitude"],
            "longitude": session["longitude"],
            "rewarded_at": datetime.now(),
            "user_id": user_id,
        })
        _increment_daily_count(user_id)

    # ------------------------------------------------------------------
    # Build response
    # ------------------------------------------------------------------
    response = {
        "success": overall_status == "accepted",
        "status": overall_status,
        "session_id": session_id,

        # AI Prediction results
        "ai_prediction": {
            "is_garbage": garbage_result["is_garbage"],
            "detected_labels": garbage_result["detected_labels"],
            "confidence_score": garbage_result["confidence_score"],
            "top_predictions": garbage_result["all_predictions"][:5],
            "warning": garbage_warning,
        },

        # Image comparison results
        "image_comparison": {
            "ssim_score": comparison_result["ssim_score"],
            "pixel_difference": comparison_result["pixel_difference"],
            "is_different_enough": comparison_result["is_different_enough"],
            "status": comparison_result["status"],
            "reason": comparison_result["reason"],
        },

        # Anti-cheating rule results
        "validation_rules": {
            "all_passed": validation_result["all_passed"],
            "checks": validation_result["checks"],
        },

        # Overall result
        "rejection_reasons": rejection_reasons if rejection_reasons else None,
    }

    return jsonify(response), 200 if overall_status == "accepted" else 400


# ===================================================================
# BONUS: GET /session-status — Check a session's current state
# ===================================================================
@verification_bp.route("/session-status/<session_id>", methods=["GET"])
def session_status(session_id):
    """Quick endpoint to check the status of a verification session."""
    session = _sessions.get(session_id)
    if not session:
        return jsonify({"success": False, "reason": "Session not found."}), 404

    return jsonify({
        "success": True,
        "session_id": session_id,
        "status": session["status"],
        "user_id": session["user_id"],
        "before_uploaded": session["before_image_path"] is not None,
        "after_uploaded": session["after_image_path"] is not None,
        "before_timestamp": session["before_timestamp"].isoformat() if session["before_timestamp"] else None,
        "after_timestamp": session["after_timestamp"].isoformat() if session["after_timestamp"] else None,
    }), 200
