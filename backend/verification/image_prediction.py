"""
image_prediction.py — MobileNetV2 Image Classification via ONNX Runtime
========================================================================
Uses a pre-trained MobileNetV2 model (trained on ImageNet) to classify
uploaded images and return the top-N predicted labels with confidence scores.

We use ONNX Runtime instead of TensorFlow for broader Python version
compatibility (including Python 3.14+). The model is auto-downloaded on
first run and cached locally.
"""

import os
import json
import urllib.request
import numpy as np
from PIL import Image
import io
import base64
import onnxruntime as ort

# ---------------------------------------------------------------
# Model & labels download URLs
# MobileNetV2 ONNX from the ONNX Model Zoo (pre-trained on ImageNet)
# ---------------------------------------------------------------
MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "mobilenetv2-7.onnx")
LABELS_PATH = os.path.join(MODEL_DIR, "imagenet_labels.json")

MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-7.onnx"
LABELS_URL = "https://raw.githubusercontent.com/anishathalye/imagenet-simple-labels/master/imagenet-simple-labels.json"


def _download_if_needed():
    """Download the MobileNetV2 ONNX model and ImageNet labels if not cached."""
    os.makedirs(MODEL_DIR, exist_ok=True)

    if not os.path.exists(MODEL_PATH):
        print(f"[GeoClean AI] Downloading MobileNetV2 ONNX model (~14MB)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print(f"[GeoClean AI] Model saved to {MODEL_PATH}")

    if not os.path.exists(LABELS_PATH):
        print(f"[GeoClean AI] Downloading ImageNet labels...")
        urllib.request.urlretrieve(LABELS_URL, LABELS_PATH)
        print(f"[GeoClean AI] Labels saved to {LABELS_PATH}")


# ---------------------------------------------------------------
# Load the model ONCE at module import
# ---------------------------------------------------------------
print("[GeoClean AI] Initializing MobileNetV2 ONNX model...")
_download_if_needed()

_session = ort.InferenceSession(MODEL_PATH)
_input_name = _session.get_inputs()[0].name

with open(LABELS_PATH, "r") as f:
    _labels = json.load(f)  # List of 1000 ImageNet class names

print(f"[GeoClean AI] MobileNetV2 loaded ✓ ({len(_labels)} classes)")


def _softmax(x):
    """Compute softmax probabilities from raw logits."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()


def _load_image_from_base64(base64_str: str) -> Image.Image:
    """
    Decode a base64-encoded image string into a PIL Image.
    Handles the 'data:image/...;base64,' prefix if present.
    """
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,")[1]
    image_bytes = base64.b64decode(base64_str)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return image


def _load_image_from_path(filepath: str) -> Image.Image:
    """Load a PIL Image from a filesystem path."""
    return Image.open(filepath).convert("RGB")


def _prepare_image(image: Image.Image) -> np.ndarray:
    """
    Resize and preprocess an image for MobileNetV2 ONNX model.
    
    MobileNetV2 expects:
      - Input shape: (1, 3, 224, 224) — NCHW format
      - Normalized with ImageNet mean=[0.485, 0.456, 0.406] and std=[0.229, 0.224, 0.225]
    """
    # Resize to 224x224
    image = image.resize((224, 224))

    # Convert to numpy float32 array and normalize to [0, 1]
    img_array = np.array(image, dtype=np.float32) / 255.0

    # Apply ImageNet normalization
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    img_array = (img_array - mean) / std

    # Transpose from HWC to CHW format and add batch dimension → (1, 3, 224, 224)
    img_array = np.transpose(img_array, (2, 0, 1))
    img_array = np.expand_dims(img_array, axis=0)

    return img_array


def predict_image(image_source, top_n: int = 10) -> list:
    """
    Run MobileNetV2 inference on an image and return top predictions.

    Args:
        image_source: Either a base64 string or a filesystem path to the image.
        top_n: Number of top predictions to return (default: 10).

    Returns:
        A list of dicts, each with:
            - 'label': Simplified class name (e.g., 'water bottle')
            - 'description': Same as label (ImageNet simple labels)
            - 'confidence': Float between 0.0 and 1.0
    """
    # Step 1: Load the image
    if isinstance(image_source, str) and (
        image_source.startswith("data:") or len(image_source) > 260
    ):
        image = _load_image_from_base64(image_source)
    else:
        image = _load_image_from_path(image_source)

    # Step 2: Preprocess for MobileNetV2
    preprocessed = _prepare_image(image)

    # Step 3: Run ONNX inference
    outputs = _session.run(None, {_input_name: preprocessed})
    logits = outputs[0][0]  # Shape: (1000,)

    # Step 4: Convert logits to probabilities
    probabilities = _softmax(logits)

    # Step 5: Get top-N predictions
    top_indices = np.argsort(probabilities)[::-1][:top_n]

    results = []
    for idx in top_indices:
        label = _labels[idx] if idx < len(_labels) else f"class_{idx}"
        results.append({
            "label": label.replace(" ", "_"),
            "description": label,
            "confidence": round(float(probabilities[idx]), 4),
        })

    return results
