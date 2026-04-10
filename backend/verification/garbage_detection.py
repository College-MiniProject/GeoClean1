"""
garbage_detection.py — Garbage/Trash Detection from Image Predictions
=====================================================================
Takes the prediction results from MobileNetV2 and determines whether
the image likely contains garbage or trash by matching predicted labels
against a curated keyword list.

This is a heuristic approach suitable for a college project — it won't
catch everything, but it makes automated cheating significantly harder.
"""

# ---------------------------------------------------------------
# Garbage-related keywords to match against MobileNetV2 labels
# These are drawn from ImageNet categories that commonly appear
# in photos of litter, waste, or unclean environments.
# ---------------------------------------------------------------
GARBAGE_KEYWORDS = [
    # Direct trash/waste terms
    "plastic", "bottle", "trash", "garbage", "waste", "litter", "bin",
    "bag", "container", "carton", "packet", "wrapper",

    # Specific ImageNet classes commonly found in garbage scenes
    "water_bottle", "pop_bottle", "wine_bottle", "beer_bottle",
    "plastic_bag", "grocery_store", "shopping_cart",
    "crate", "bucket", "pail",
    "diaper", "Band_Aid", "envelope",
    "paper_towel", "toilet_tissue",
    "can", "tin_can", "beer_glass",
    "cup", "coffeepot", "pitcher",

    # Containers and packaging
    "jug", "vase", "pot", "tub", "barrel",
    "box", "chest", "clog",
    "tray", "plate", "bowl",

    # Debris / construction-adjacent
    "nail", "screw", "chain", "hook",
    "tire", "rubber",

    # General dirtiness indicators
    "mud", "soil", "dirt",
]

# Minimum confidence threshold for a prediction to count
CONFIDENCE_THRESHOLD = 0.05


def detect_garbage(predictions: list) -> dict:
    """
    Analyze MobileNetV2 predictions to determine if garbage is present.

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
        label = pred["label"].lower()
        description = pred["description"].lower()
        confidence = pred["confidence"]

        # Skip predictions below minimum confidence
        if confidence < CONFIDENCE_THRESHOLD:
            continue

        # Check if any garbage keyword appears in the label or description
        for keyword in GARBAGE_KEYWORDS:
            if keyword in label or keyword in description:
                detected_labels.append({
                    "label": pred["label"],
                    "description": pred["description"],
                    "confidence": confidence,
                    "matched_keyword": keyword,
                })
                max_confidence = max(max_confidence, confidence)
                break  # One match per prediction is enough

    # Determine if the image contains garbage
    is_garbage = len(detected_labels) > 0

    return {
        "is_garbage": is_garbage,
        "detected_labels": detected_labels,
        "confidence_score": round(max_confidence, 4),
        "all_predictions": predictions,
    }
