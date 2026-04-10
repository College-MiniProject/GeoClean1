"""
validation_rules.py — Anti-Cheating Validation Rules
=====================================================
Implements rule-based checks to prevent reward exploitation (GeoCoin farming).

Rules:
1. Location Cooldown — Same GPS coordinates can't be rewarded within 24 hours
2. Minimum Time Gap — At least X minutes must pass between before/after uploads
3. Daily Reward Limit — Maximum N rewards per user per day

These rules work alongside the AI detection and image comparison
to create a multi-layered anti-cheating system.
"""

import math
from datetime import datetime, timedelta

# ---------------------------------------------------------------
# Configuration constants (easy to tune)
# ---------------------------------------------------------------

# How close two GPS points must be to count as "same location" (in meters)
LOCATION_RADIUS_METERS = 100

# Cooldown period for the same location (in hours)
LOCATION_COOLDOWN_HOURS = 24

# Minimum time between before and after images (in minutes)
MIN_TIME_BETWEEN_IMAGES_MINUTES = 5

# Maximum cleanups a single user can claim rewards for per day
DAILY_REWARD_LIMIT = 5


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two GPS coordinates
    using the Haversine formula. Returns distance in meters.

    This is more accurate than simple Euclidean distance for GPS coordinates.
    """
    R = 6371000  # Earth's radius in meters

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def validate_location_cooldown(
    latitude: float,
    longitude: float,
    recent_rewards: list,
) -> dict:
    """
    Check if the same location has been rewarded within the cooldown period.

    Args:
        latitude: Current cleanup latitude.
        longitude: Current cleanup longitude.
        recent_rewards: List of dicts from the database, each with:
            - 'latitude': float
            - 'longitude': float
            - 'rewarded_at': datetime object

    Returns:
        A dict with:
            - 'passed': True if no conflict, False if location was recently rewarded
            - 'reason': Explanation string
    """
    if latitude is None or longitude is None:
        return {
            "passed": False,
            "reason": "GPS coordinates are missing. Location verification required.",
        }

    now = datetime.now()
    cooldown_cutoff = now - timedelta(hours=LOCATION_COOLDOWN_HOURS)

    for reward in recent_rewards:
        r_lat = reward.get("latitude")
        r_lng = reward.get("longitude")
        r_time = reward.get("rewarded_at")

        # Skip entries without valid GPS
        if r_lat is None or r_lng is None:
            continue

        # Check if within cooldown period
        if r_time and r_time > cooldown_cutoff:
            # Check if within the location radius
            distance = _haversine_distance(latitude, longitude, r_lat, r_lng)
            if distance <= LOCATION_RADIUS_METERS:
                hours_ago = round((now - r_time).total_seconds() / 3600, 1)
                return {
                    "passed": False,
                    "reason": (
                        f"This location was already rewarded {hours_ago} hours ago "
                        f"(within {LOCATION_RADIUS_METERS}m radius). "
                        f"Please wait {LOCATION_COOLDOWN_HOURS}h between cleanups at the same spot."
                    ),
                }

    return {
        "passed": True,
        "reason": "Location cooldown check passed.",
    }


def validate_time_gap(before_timestamp: datetime, after_timestamp: datetime) -> dict:
    """
    Ensure a minimum time gap exists between before and after image uploads.
    This prevents users from rapidly uploading pre-taken photos.

    Args:
        before_timestamp: When the 'before' image was uploaded.
        after_timestamp: When the 'after' image was uploaded.

    Returns:
        A dict with:
            - 'passed': True if enough time has passed
            - 'time_elapsed_minutes': How many minutes elapsed
            - 'reason': Explanation string
    """
    if before_timestamp is None or after_timestamp is None:
        return {
            "passed": False,
            "time_elapsed_minutes": 0,
            "reason": "Upload timestamps are missing. Cannot verify time gap.",
        }

    elapsed = after_timestamp - before_timestamp
    elapsed_minutes = elapsed.total_seconds() / 60

    if elapsed_minutes < MIN_TIME_BETWEEN_IMAGES_MINUTES:
        return {
            "passed": False,
            "time_elapsed_minutes": round(elapsed_minutes, 1),
            "reason": (
                f"Only {elapsed_minutes:.1f} minutes between uploads. "
                f"Minimum required: {MIN_TIME_BETWEEN_IMAGES_MINUTES} minutes. "
                "Please allow enough time for actual cleaning."
            ),
        }

    return {
        "passed": True,
        "time_elapsed_minutes": round(elapsed_minutes, 1),
        "reason": f"Time gap check passed ({elapsed_minutes:.1f} minutes elapsed).",
    }


def validate_daily_limit(user_id: str, today_reward_count: int) -> dict:
    """
    Check if the user has exceeded their daily reward limit.

    Args:
        user_id: The user's identifier (email or ID).
        today_reward_count: How many rewards the user has already received today.

    Returns:
        A dict with:
            - 'passed': True if under the limit
            - 'remaining': How many rewards left today
            - 'reason': Explanation string
    """
    if today_reward_count >= DAILY_REWARD_LIMIT:
        return {
            "passed": False,
            "remaining": 0,
            "reason": (
                f"Daily reward limit reached ({DAILY_REWARD_LIMIT} per day). "
                "Come back tomorrow to earn more GeoCoins!"
            ),
        }

    remaining = DAILY_REWARD_LIMIT - today_reward_count
    return {
        "passed": True,
        "remaining": remaining,
        "reason": f"Daily limit check passed. {remaining} rewards remaining today.",
    }


def run_all_validations(
    latitude: float,
    longitude: float,
    before_timestamp: datetime,
    after_timestamp: datetime,
    user_id: str,
    today_reward_count: int,
    recent_rewards: list,
) -> dict:
    """
    Run ALL anti-cheating validations in sequence and return a combined result.

    Args:
        latitude, longitude: GPS coordinates of the cleanup.
        before_timestamp: When the 'before' image was uploaded.
        after_timestamp: When the 'after' image was uploaded.
        user_id: The user's identifier.
        today_reward_count: How many rewards the user already got today.
        recent_rewards: List of recent reward records for location checking.

    Returns:
        A dict with:
            - 'all_passed': True if ALL checks passed
            - 'checks': Dict with results of each individual check
            - 'failed_reasons': List of reasons for any failures
    """
    results = {}
    failed_reasons = []

    # Check 1: Location cooldown
    location_check = validate_location_cooldown(latitude, longitude, recent_rewards)
    results["location_cooldown"] = location_check
    if not location_check["passed"]:
        failed_reasons.append(location_check["reason"])

    # Check 2: Time gap between uploads
    time_check = validate_time_gap(before_timestamp, after_timestamp)
    results["time_gap"] = time_check
    if not time_check["passed"]:
        failed_reasons.append(time_check["reason"])

    # Check 3: Daily reward limit
    daily_check = validate_daily_limit(user_id, today_reward_count)
    results["daily_limit"] = daily_check
    if not daily_check["passed"]:
        failed_reasons.append(daily_check["reason"])

    return {
        "all_passed": len(failed_reasons) == 0,
        "checks": results,
        "failed_reasons": failed_reasons,
    }
