"""
image_comparison.py — Before/After Image Comparison using OpenCV
================================================================
Compares "before cleaning" and "after cleaning" images to calculate
a difference score. Uses two complementary techniques:

1. Structural Similarity Index (SSIM) — measures perceptual similarity
2. Absolute Difference (cv2.absdiff) — measures raw pixel changes

If the images are too similar (low difference), the cleaning is likely
fake. If the difference is high enough, the cleaning is accepted.
"""

import cv2
import numpy as np
import base64
import os
from skimage.metrics import structural_similarity as ssim


def _load_image_cv2(image_source: str) -> np.ndarray:
    """
    Load an image into OpenCV format (BGR numpy array).
    Accepts either a base64 string or a filesystem path.
    """
    if isinstance(image_source, str) and (
        image_source.startswith("data:") or len(image_source) > 260
    ):
        # It's a base64 string — decode it
        if "base64," in image_source:
            image_source = image_source.split("base64,")[1]
        image_bytes = base64.b64decode(image_source)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    else:
        # It's a file path
        image = cv2.imread(image_source)

    if image is None:
        raise ValueError(f"Failed to load image from source")

    return image


def _resize_to_match(img1: np.ndarray, img2: np.ndarray) -> tuple:
    """
    Resize both images to the same dimensions for fair comparison.
    Uses the smaller of the two dimensions.
    """
    # Use a standard comparison size (reduces processing time)
    target_size = (300, 300)
    img1_resized = cv2.resize(img1, target_size)
    img2_resized = cv2.resize(img2, target_size)
    return img1_resized, img2_resized


def calculate_ssim(before_source: str, after_source: str) -> float:
    """
    Calculate Structural Similarity Index (SSIM) between two images.

    SSIM ranges from -1 to 1:
        - 1.0 = perfectly identical images
        - 0.0 = no structural similarity
        - Values > 0.9 typically indicate very similar images

    Args:
        before_source: Base64 string or filepath to the 'before' image.
        after_source: Base64 string or filepath to the 'after' image.

    Returns:
        SSIM score as a float.
    """
    # Load and resize images
    img1 = _load_image_cv2(before_source)
    img2 = _load_image_cv2(after_source)
    img1, img2 = _resize_to_match(img1, img2)

    # Convert to grayscale (SSIM works on single-channel images)
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Calculate SSIM
    score = ssim(gray1, gray2)
    return round(float(score), 4)


def calculate_pixel_difference(before_source: str, after_source: str) -> float:
    """
    Calculate the mean absolute pixel difference between two images.
    Uses cv2.absdiff to find per-pixel differences, then averages them.

    Returns a normalized difference score (0.0 to 1.0):
        - 0.0 = identical images
        - 1.0 = completely different images (max possible difference)

    Args:
        before_source: Base64 string or filepath to the 'before' image.
        after_source: Base64 string or filepath to the 'after' image.

    Returns:
        Normalized mean difference score.
    """
    # Load and resize images
    img1 = _load_image_cv2(before_source)
    img2 = _load_image_cv2(after_source)
    img1, img2 = _resize_to_match(img1, img2)

    # Compute absolute difference
    diff = cv2.absdiff(img1, img2)

    # Calculate mean difference normalized to [0, 1]
    mean_diff = np.mean(diff) / 255.0
    return round(float(mean_diff), 4)


def compare_images(before_source: str, after_source: str) -> dict:
    """
    Full comparison of before/after images using both SSIM and pixel difference.

    Decision logic:
        - SSIM > 0.90 AND pixel_diff < 0.05 → REJECTED (images too similar, fake cleanup)
        - SSIM > 0.85 AND pixel_diff < 0.08 → SUSPICIOUS (borderline case)
        - Otherwise → ACCEPTED (meaningful visual change detected)

    Args:
        before_source: Base64 string or filepath to the 'before' image.
        after_source: Base64 string or filepath to the 'after' image.

    Returns:
        A dict with:
            - 'ssim_score': SSIM value
            - 'pixel_difference': Normalized pixel diff
            - 'is_different_enough': Boolean — True means cleaning looks real
            - 'status': 'accepted' | 'rejected' | 'suspicious'
            - 'reason': Human-readable explanation
    """
    try:
        ssim_score = calculate_ssim(before_source, after_source)
        pixel_diff = calculate_pixel_difference(before_source, after_source)
    except Exception as e:
        return {
            "ssim_score": None,
            "pixel_difference": None,
            "is_different_enough": False,
            "status": "error",
            "reason": f"Image comparison failed: {str(e)}",
        }

    # ---------------------------------------------------------------
    # Decision thresholds (tuned for real-world phone camera photos)
    # ---------------------------------------------------------------
    if ssim_score > 0.90 and pixel_diff < 0.05:
        # Almost identical images — clearly fake
        return {
            "ssim_score": ssim_score,
            "pixel_difference": pixel_diff,
            "is_different_enough": False,
            "status": "rejected",
            "reason": (
                f"Images are nearly identical (SSIM={ssim_score}, diff={pixel_diff}). "
                "This does not look like a real cleanup. Please submit genuine before/after photos."
            ),
        }

    elif ssim_score > 0.85 and pixel_diff < 0.08:
        # Borderline case — suspicious but not conclusive
        return {
            "ssim_score": ssim_score,
            "pixel_difference": pixel_diff,
            "is_different_enough": False,
            "status": "suspicious",
            "reason": (
                f"Images look very similar (SSIM={ssim_score}, diff={pixel_diff}). "
                "The change is too minor to confirm a real cleanup. Try taking a clearer after photo."
            ),
        }

    else:
        # Meaningful difference detected — accept
        return {
            "ssim_score": ssim_score,
            "pixel_difference": pixel_diff,
            "is_different_enough": True,
            "status": "accepted",
            "reason": (
                f"Visual change detected (SSIM={ssim_score}, diff={pixel_diff}). "
                "The before and after images show a meaningful difference."
            ),
        }
