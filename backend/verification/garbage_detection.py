"""
garbage_detection.py — Garbage/Trash Detection from Image Predictions
=====================================================================
Takes the prediction results from MobileNetV2 and determines whether
the image likely contains garbage or trash by matching predicted labels
against a STRICT keyword list.

Also includes image quality validation to reject blank, black, or
otherwise useless images BEFORE AI classification runs.

This is a heuristic approach suitable for a college project — it won't
catch everything, but it makes automated cheating significantly harder.
"""

import base64
import io
import numpy as np
from PIL import Image, ImageStat

# ---------------------------------------------------------------
# STRICT garbage-related keywords — ONLY actual trash items
# Removed vague words like "bag", "cup", "bowl", "pot" that match
# literally anything. These are EXACT ImageNet class names that
# genuinely indicate waste/litter.
# ---------------------------------------------------------------
GARBAGE_KEYWORDS = [
    # Direct garbage terms
    "water bottle",
    "pop bottle",
    "wine bottle",
    "beer bottle",
    "plastic bag",
    "diaper",
    "Band Aid",
    "paper towel",
    "toilet tissue",
    "tin can",
    "cardboard",
    "envelope",
    "shopping cart",    # implies litter area
    "garbage truck",
    "crate",
    "bucket",
    "pail",
]

# Minimum confidence for a prediction to be considered real
# 5% was way too low — a black image could match with low confidence.
# 15% is more realistic for MobileNetV2 on actual objects.
CONFIDENCE_THRESHOLD = 0.15

# Minimum number of garbage labels needed to classify as garbage
# Requiring 1+ match with high confidence prevents random false positives
MIN_MATCHES_REQUIRED = 1


def validate_image_quality(image_source) -> dict:
    """
    Check if an image is actually a real photograph vs a blank/black/white
    solid-color image, or a covered camera lens. Uses pixel variance and
    edge detection.

    Args:
        image_source: Base64 string or file path to the image.

    Returns:
        A dict with:
            - 'is_valid' (bool): True if the image looks like a real photo
            - 'reason' (str): Explanation of the result
            - 'variance' (float): Pixel variance value
            - 'edge_density' (float): Percentage of edges detected
    """
    try:
        # Load image
        if isinstance(image_source, str) and (
            image_source.startswith("data:") or len(image_source) > 260
        ):
            if "base64," in image_source:
                image_source = image_source.split("base64,")[1]
            image_bytes = base64.b64decode(image_source)
            img = Image.open(io.BytesIO(image_bytes))
        else:
            img = Image.open(image_source)

        img = img.convert("RGB")
        img_resized = img.resize((224, 224))
        img_array = np.array(img_resized)

        # --- CHECK 1: Pixel Variance ---
        # Solid color images (black, white, any color) have near-zero variance
        gray = np.mean(img_array, axis=2)  # Convert to grayscale
        variance = float(np.var(gray))

        if variance < 50:
            return {
                "is_valid": False,
                "reason": f"Image appears to be a solid color or blank (variance={variance:.1f}). "
                          "Please upload a real photograph of the area.",
                "variance": round(variance, 2),
                "edge_density": 0.0,
            }

        # --- CHECK 2: Edge Density ---
        # Real photos have edges (objects, textures). Blank/blurry images don't.
        # Simple Sobel-like edge detection using numpy
        dx = np.abs(np.diff(gray, axis=1))
        dy = np.abs(np.diff(gray, axis=0))
        edge_pixels = np.sum(dx > 15) + np.sum(dy > 15)
        total_pixels = gray.size
        edge_density = float(edge_pixels) / total_pixels

        if edge_density < 0.02:
            return {
                "is_valid": False,
                "reason": f"Image has no visible objects or detail (edge density={edge_density:.3f}). "
                          "Please upload a clear photo showing garbage.",
                "variance": round(variance, 2),
                "edge_density": round(edge_density, 4),
            }

        # --- CHECK 3: Color Distribution ---
        # Real outdoor photos have varied colors. Synthetic/fake images often don't.
        r_std = float(np.std(img_array[:, :, 0]))
        g_std = float(np.std(img_array[:, :, 1]))
        b_std = float(np.std(img_array[:, :, 2]))
        avg_color_std = (r_std + g_std + b_std) / 3

        if avg_color_std < 8:
            return {
                "is_valid": False,
                "reason": "Image has almost no color variation — appears fake or artificially generated.",
                "variance": round(variance, 2),
                "edge_density": round(edge_density, 4),
            }

        return {
            "is_valid": True,
            "reason": "Image quality check passed.",
            "variance": round(variance, 2),
            "edge_density": round(edge_density, 4),
        }

    except Exception as e:
        return {
            "is_valid": False,
            "reason": f"Failed to validate image: {str(e)}",
            "variance": 0.0,
            "edge_density": 0.0,
        }


def detect_garbage(predictions: list) -> dict:
    """
    Analyze MobileNetV2 predictions to determine if garbage is present.

    Uses EXACT matching against known ImageNet trash labels, with a high
    confidence threshold to avoid false positives.

    Args:
        predictions: List of prediction dicts from image_prediction.predict_image()
            Each dict has 'label', 'description', and 'confidence'.

    Returns:
        A dict with:
            - 'is_garbage' (bool): True if garbage-related objects were detected
            - 'detected_labels' (list): Labels that matched garbage keywords
            - 'confidence_score' (float): Highest confidence among matched labels
            - 'all_predictions' (list): The full prediction list for transparency
    """
    detected_labels = []
    max_confidence = 0.0

    for pred in predictions:
        description = pred["description"].lower()
        confidence = pred["confidence"]

        # Skip predictions below the raised confidence threshold
        if confidence < CONFIDENCE_THRESHOLD:
            continue

        # Check against STRICT garbage keywords (exact ImageNet class names)
        for keyword in GARBAGE_KEYWORDS:
            if keyword.lower() in description:
                detected_labels.append({
                    "label": pred["label"],
                    "description": pred["description"],
                    "confidence": confidence,
                    "matched_keyword": keyword,
                })
                max_confidence = max(max_confidence, confidence)
                break  # One match per prediction is enough

    # Must have at least MIN_MATCHES_REQUIRED garbage detections
    is_garbage = len(detected_labels) >= MIN_MATCHES_REQUIRED

    return {
        "is_garbage": is_garbage,
        "detected_labels": detected_labels,
        "confidence_score": round(max_confidence, 4),
        "all_predictions": predictions,
    }
