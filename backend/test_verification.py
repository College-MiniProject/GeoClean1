"""
test_verification.py — Quick Test Script for GeoClean AI Verification
=====================================================================
Tests the three verification endpoints using sample images.

Usage:
    1. Start the Flask server:  python app.py
    2. In another terminal:     python test_verification.py
"""

import requests
import base64
import time
import json
import sys
import os

# Server URL (change if running on a different port)
BASE_URL = "http://localhost:5050"


def create_test_image(color=(100, 150, 200), size=(224, 224)):
    """Create a simple test image as base64."""
    try:
        from PIL import Image
        import io
        img = Image.new("RGB", size, color)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except ImportError:
        print("Pillow not installed. Run: pip install Pillow")
        sys.exit(1)


def test_upload_before():
    """Test Step 1: Upload a before image."""
    print("\n" + "=" * 60)
    print("TEST 1: POST /upload-before")
    print("=" * 60)

    image_b64 = create_test_image(color=(80, 120, 60))  # greenish "outdoors"

    payload = {
        "image": image_b64,
        "latitude": 17.3850,
        "longitude": 78.4867,
        "user_id": "testuser@college.edu",
    }

    response = requests.post(f"{BASE_URL}/upload-before", json=payload)
    data = response.json()

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")

    return data.get("session_id")


def test_upload_after(session_id):
    """Test Step 2: Upload an after image."""
    print("\n" + "=" * 60)
    print("TEST 2: POST /upload-after")
    print("=" * 60)

    # Create a noticeably different image (cleaner-looking)
    image_b64 = create_test_image(color=(200, 220, 180))  # lighter "clean" scene

    payload = {
        "image": image_b64,
        "session_id": session_id,
    }

    response = requests.post(f"{BASE_URL}/upload-after", json=payload)
    data = response.json()

    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(data, indent=2)}")

    return data.get("success", False)


def test_validate_cleaning(session_id):
    """Test Step 3: Run full validation."""
    print("\n" + "=" * 60)
    print("TEST 3: POST /validate-cleaning")
    print("=" * 60)

    payload = {"session_id": session_id}

    response = requests.post(f"{BASE_URL}/validate-cleaning", json=payload)
    data = response.json()

    print(f"Status: {response.status_code}")
    print(f"\n--- AI Prediction ---")
    ai = data.get("ai_prediction", {})
    print(f"  Is Garbage: {ai.get('is_garbage')}")
    print(f"  Confidence: {ai.get('confidence_score')}")
    if ai.get("detected_labels"):
        for label in ai["detected_labels"][:3]:
            print(f"    → {label['description']} ({label['confidence']:.1%})")
    if ai.get("warning"):
        print(f"  ⚠ Warning: {ai['warning']}")

    print(f"\n--- Image Comparison ---")
    comp = data.get("image_comparison", {})
    print(f"  SSIM Score: {comp.get('ssim_score')}")
    print(f"  Pixel Diff: {comp.get('pixel_difference')}")
    print(f"  Status: {comp.get('status')}")

    print(f"\n--- Validation Rules ---")
    rules = data.get("validation_rules", {})
    print(f"  All Passed: {rules.get('all_passed')}")
    for check_name, check_result in rules.get("checks", {}).items():
        print(f"    {check_name}: {'✓' if check_result.get('passed') else '✗'} — {check_result.get('reason')}")

    print(f"\n--- Overall Result ---")
    print(f"  Status: {data.get('status', 'unknown').upper()}")
    if data.get("rejection_reasons"):
        for reason in data["rejection_reasons"]:
            print(f"  ✗ {reason}")
    else:
        print("  ✓ Cleaning validated successfully!")


def test_identical_images():
    """Test that uploading identical before/after images gets rejected."""
    print("\n" + "=" * 60)
    print("TEST 4: Identical Images (should be REJECTED)")
    print("=" * 60)

    same_image = create_test_image(color=(100, 100, 100))

    # Upload before
    r1 = requests.post(f"{BASE_URL}/upload-before", json={
        "image": same_image,
        "latitude": 17.3850,
        "longitude": 78.4867,
        "user_id": "cheater@test.com",
    })
    session_id = r1.json().get("session_id")

    # Upload identical after
    requests.post(f"{BASE_URL}/upload-after", json={
        "image": same_image,
        "session_id": session_id,
    })

    # Validate
    r3 = requests.post(f"{BASE_URL}/validate-cleaning", json={"session_id": session_id})
    data = r3.json()

    status = data.get("status", "unknown")
    print(f"  Result: {status.upper()}")
    if status == "rejected":
        print("  ✓ Correctly caught identical images!")
    else:
        print("  ✗ Should have been rejected (identical images)")


if __name__ == "__main__":
    print("=" * 60)
    print("  GeoClean AI Verification — Test Suite")
    print(f"  Server: {BASE_URL}")
    print("=" * 60)

    # Check server is running
    try:
        requests.get(BASE_URL, timeout=3)
    except requests.ConnectionError:
        print(f"\n❌ Cannot connect to {BASE_URL}")
        print("   Start the server first: python app.py")
        sys.exit(1)

    # Run tests
    session_id = test_upload_before()
    if session_id:
        test_upload_after(session_id)
        test_validate_cleaning(session_id)

    test_identical_images()

    print("\n" + "=" * 60)
    print("  All tests completed!")
    print("=" * 60)
