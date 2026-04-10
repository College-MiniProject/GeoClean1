# GeoClean AI Verification Module
# ================================
# This package provides intelligent garbage detection and anti-cheating
# validation for the GeoClean cleanup reward system.
#
# Modules:
#   - image_prediction: TensorFlow MobileNetV2 image classification
#   - garbage_detection: Keyword-based garbage identification from predictions
#   - image_comparison: OpenCV before/after scene comparison (SSIM + absdiff)
#   - validation_rules: Anti-cheating rules (location, time, daily caps)
