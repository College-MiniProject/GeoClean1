import os
import shutil
import tempfile
import math
import json
from datetime import datetime
from PIL import Image, ExifTags
import imagehash
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import uvicorn
from dotenv import load_dotenv

# Load environment variables (for GEMINI_API_KEY)
load_dotenv()

app = FastAPI(title="GeoClean AI Verification - Gemini & ImageHash Edition")

# Configure Gemini AI
# Make sure you have GEMINI_API_KEY set in your .env file!
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# We use gemini-1.5-flash because it's exceptionally fast, free-tier friendly, and great with images
vision_model = genai.GenerativeModel('gemini-1.5-flash')

UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "geoclean_smart_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# -----------------------------------------------------------------------------------------
# 1. EXIF VALIDATION (Time & Distance)
# -----------------------------------------------------------------------------------------
def get_decimal_from_dms(dms, ref):
    decimal = float(dms[0]) + (float(dms[1]) / 60.0) + (float(dms[2]) / 3600.0)
    return -decimal if ref in ['S', 'W'] else decimal

def extract_metadata(image_path: str):
    try:
        img = Image.open(image_path)
        exif_info = img._getexif()
    except Exception:
        return {"datetime": None, "gps": None}
        
    metadata = {"datetime": None, "gps": None}
    if not exif_info:
        return metadata
        
    for tag_id, value in exif_info.items():
        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
        if tag_name == "DateTimeOriginal":
            try:
                metadata["datetime"] = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                pass
        elif tag_name == "GPSInfo":
            gps_data = {}
            for t in value:
                sub_tag = ExifTags.GPSTAGS.get(t, t)
                gps_data[sub_tag] = value[t]
                
            if all(k in gps_data for k in ["GPSLatitude", "GPSLatitudeRef", "GPSLongitude", "GPSLongitudeRef"]):
                try:
                    lat = get_decimal_from_dms(gps_data["GPSLatitude"], gps_data["GPSLatitudeRef"])
                    lon = get_decimal_from_dms(gps_data["GPSLongitude"], gps_data["GPSLongitudeRef"])
                    metadata["gps"] = (lat, lon)
                except Exception:
                    pass
    return metadata

def haversine_distance(coord1, coord2):
    R = 6371000
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# -----------------------------------------------------------------------------------------
# 2. IMAGE HASHING (Cheat Prevention)
# -----------------------------------------------------------------------------------------
def are_images_identical(img1_path: str, img2_path: str) -> bool:
    """ Computes the Perceptual Hash of both images. If difference is 0, they uploaded the same image. """
    hash1 = imagehash.phash(Image.open(img1_path))
    hash2 = imagehash.phash(Image.open(img2_path))
    # A difference of 0-2 usually means it's the exact same image (possibly compressed/cropped)
    return (hash1 - hash2) < 3

# -----------------------------------------------------------------------------------------
# 3. GEMINI AI VLM JUDGEMENT (Location Match & Trash Detection)
# -----------------------------------------------------------------------------------------
def verify_with_gemini(before_path: str, after_path: str):
    """ Uploads both images to Gemini and asks it to evaluate cleanliness & location match. """
    if not api_key:
        return {"error": "GEMINI_API_KEY is missing. Cannot run visual analysis."}

    try:
        # Load images for Gemini
        img_before = Image.open(before_path)
        img_after = Image.open(after_path)
        
        prompt = """
        You are a strict, objective environmental judge. I am providing you with two images: 
        1. The first image is the 'Before' state.
        2. The second image is the 'After' state.
        
        Please analyze them and answer these two questions:
        Question A: Are these two photos taken in the exact same physical location? (Look at the background, ground texture, etc.)
        Question B: Has the trash/litter visibly been removed in the 'After' photo? Is the area now clean?
        
        Return exactly and ONLY a JSON object in this format:
        {
            "same_location": true/false,
            "trash_removed": true/false,
            "reasoning": "A 1-sentence explanation of what you see."
        }
        """
        
        # Pass the prompt and both images to Gemini Flash
        response = vision_model.generate_content([prompt, img_before, img_after])
        
        # Clean up the output to parse the JSON
        response_text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(response_text)
        return data

    except Exception as e:
        return {"error": str(e)}

# -----------------------------------------------------------------------------------------
# FASTAPI PIPELINE ENDPOINT
# -----------------------------------------------------------------------------------------
@app.post("/verify-cleanup")
async def verify_cleanup(before_img: UploadFile = File(...), after_img: UploadFile = File(...)):
    status = "Passed"
    reasons = []

    before_path = os.path.join(UPLOAD_DIR, "before_" + before_img.filename)
    after_path = os.path.join(UPLOAD_DIR, "after_" + after_img.filename)

    with open(before_path, "wb") as buffer:
        shutil.copyfileobj(before_img.file, buffer)
    with open(after_path, "wb") as buffer:
        shutil.copyfileobj(after_img.file, buffer)

    try:
        # -------------- 1. EXIF Check --------------
        before_meta = extract_metadata(before_path)
        after_meta = extract_metadata(after_path)

        if before_meta["datetime"] and after_meta["datetime"]:
            if after_meta["datetime"] <= before_meta["datetime"]:
                status = "Failed"
                reasons.append("The 'After' photo was taken before or at the same time as the 'Before' photo.")

        if before_meta["gps"] and after_meta["gps"]:
            distance = haversine_distance(before_meta["gps"], after_meta["gps"])
            if distance > 50.0:
                status = "Failed"
                reasons.append(f"Photos were taken {distance:.0f} meters apart (Limit: 50m).")

        # -------------- 2. Image Hash / Anti-Cheat Check --------------
        if are_images_identical(before_path, after_path):
            status = "Failed"
            reasons.append("Identical images submitted. The before and after photos are the same.")
            # Skip Gemini call if it's already a proven duplicate
            return JSONResponse(content={"status": status, "reasons": reasons})

        # -------------- 3. Gemini VLM Check --------------
        gemini_result = verify_with_gemini(before_path, after_path)
        
        if "error" in gemini_result:
            status = "Failed"
            reasons.append(f"Gemini API Error: {gemini_result['error']}")
        else:
            if not gemini_result.get("same_location", False):
                status = "Failed"
                reasons.append("AI determined these photos are not taken in the same location.")
            
            if not gemini_result.get("trash_removed", False):
                status = "Failed"
                reasons.append("AI detected that the trash was not fully removed.")
                
            # If there was a failure from the AI, append the AI's reason for clarity
            if status == "Failed" and "reasoning" in gemini_result:
                reasons.append(f"AI Reasoning: {gemini_result['reasoning']}")

    finally:
        if os.path.exists(before_path): os.remove(before_path)
        if os.path.exists(after_path): os.remove(after_path)

    if status == "Failed" and not reasons:
        reasons.append("Unknown failure in verification.")

    return JSONResponse(content={
        "status": status,
        "reasons": reasons
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
