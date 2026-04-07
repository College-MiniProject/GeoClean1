import os
import uuid
import base64
import random
import webbrowser
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, render_template
import psycopg2
import psycopg2.extras
import bcrypt
from flask_cors import CORS

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app = Flask(__name__, template_folder=PROJECT_ROOT, static_folder=PROJECT_ROOT, static_url_path='')
CORS(app)
load_dotenv()

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# database connection function
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "geoclean"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "likhit@postgres"),
        port=os.getenv("DB_PORT", "5432")
    )

# Static route for uploads
@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/<path:path>")
def serve_any_html(path):
    if not path.endswith(".html"):
        return send_from_directory(app.static_folder, path)
    return render_template(path)

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    full_name = data["full_name"]
    email = data["email"]
    password = data["password"]
    department = data["department"]
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (full_name,email,password_hash,department)
            VALUES (%s,%s,%s,%s)
            """,
            (full_name, email, hashed_password.decode(), department)
        )
        conn.commit()
        return jsonify({"message": "User registered successfully"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data["email"]
    password = data["password"]

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user is None:
            return jsonify({"error": "User not found"}), 404

        stored_hash = user['password_hash']
        if bcrypt.checkpw(password.encode(), stored_hash.encode()):
            user_data = dict(user)
            if 'password_hash' in user_data:
                del user_data['password_hash']
            return jsonify({"message": "Login successful", "user": user_data}), 200
        else:
            return jsonify({"error": "Invalid password"}), 401
    finally:
        cursor.close()
        conn.close()

# Helper to save base64 image
def save_base64_image(base64_str):
    if not base64_str: return None
    # Remove data:image/png;base64, part if present
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,")[1]
    
    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(base64_str))
    
    return filename

@app.route("/missions/report", methods=["POST"])
def report_mission():
    data = request.json
    creator_email = data.get("creator_email")
    mission_type = data.get("type", "General")
    desc = data.get("description", "")
    location_text = data.get("location_text", "")
    lat = data.get("latitude")
    lng = data.get("longitude")
    before_img_b64 = data.get("before_image")
    full_address = data.get("full_address", "")
    equipment_needed = data.get("equipment_needed", "")

    filename = save_base64_image(before_img_b64)

    # Anti-Fake AI Module (Blocks solid colors/covered camera) using Pillow Variance
    if before_img_b64:
        try:
            from PIL import Image, ImageStat
            import io, base64
            # Strip base64 metadata
            header_end = before_img_b64.find(',')
            clean_b64 = before_img_b64[header_end + 1:] if header_end != -1 else before_img_b64
            img_data = base64.b64decode(clean_b64)
            img = Image.open(io.BytesIO(img_data)).convert('L')
            variance = ImageStat.Stat(img).var[0]
            if variance < 80: # Exceptionally strict blank check
                return jsonify({"error": "AI Vision Error: Image is completely blank or completely out of focus. Please ensure garbage is explicitly visible."}), 400
        except Exception as e:
            pass # fallback to accept if PIL fails

    # Simulated AI Analysis (Mock GenAI Vision)
    ai_analysis_options = [
        "Detected mostly plastic waste and synthetic debris. Moderately hazardous to local wildlife. Requires immediate bagging.",
        "Detected mixed organic and non-organic general waste. Low hazard, but high volume.",
        "Detected potential hazardous/toxic materials (unknown containers). Requires thick gloves and specialized disposal.",
        "Detected construction debris (rubble, wood). Heavy lifting required."
    ]
    ai_analysis = random.choice(ai_analysis_options)
    people_needed = random.randint(1, 4)
    # Dynamic Reward Scaling
    dynamic_reward = people_needed * 50

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check Daily Report Cap (Max 3/day)
        cursor.execute("SELECT COUNT(*) FROM missions WHERE creator_email = %s AND created_at >= CURRENT_DATE", (creator_email,))
        daily_reports = cursor.fetchone()[0]
        if daily_reports >= 3:
            return jsonify({"error": "Daily report limit reached. You can only post 3 cleanups per day."}), 429

        cursor.execute(
            """
            INSERT INTO missions (creator_email, type, description, location_text, latitude, longitude, before_image, full_address, equipment_needed, people_needed, ai_analysis, verification_status, reward)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'unverified', %s)
            """,
            (creator_email, mission_type, desc, location_text, lat, lng, filename, full_address, equipment_needed, people_needed, ai_analysis, dynamic_reward)
        )
        conn.commit()
        return jsonify({"message": "Mission reported successfully", "ai_analysis": ai_analysis, "people_needed": people_needed, "reward": dynamic_reward}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/missions", methods=["GET"])
def get_missions():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Global Expiration Deletion: delete unaccepted missions older than 14 days
        cursor.execute("DELETE FROM missions WHERE status = 'open' AND created_at < NOW() - INTERVAL '14 days'")
        
        # Auto-expire missions accepted older than 3 hours (abandoned limit)
        cursor.execute("""
            UPDATE missions SET status = 'open', accepted_by = NULL, accepted_at = NULL 
            WHERE status = 'accepted' AND accepted_at < NOW() - INTERVAL '3 hours'
        """)
        conn.commit()

        cursor.execute("SELECT * FROM missions ORDER BY created_at DESC")
        missions = [dict(row) for row in cursor.fetchall()]
        return jsonify({"missions": missions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/missions/<int:mission_id>/accept", methods=["POST"])
def accept_mission(mission_id):
    data = request.json
    email = data.get("email")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE missions SET status = 'accepted', accepted_by = %s, accepted_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'open'
            """,
            (email, mission_id)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Mission already accepted or not found"}), 400
        conn.commit()
        return jsonify({"message": "Mission accepted successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/missions/<int:mission_id>/complete", methods=["POST"])
def complete_mission(mission_id):
    data = request.json
    email = data.get("email")
    after_img_b64 = data.get("after_image")
    req_lat = data.get("latitude")
    req_lng = data.get("longitude")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check Daily Complete Cap (Max 3/day)
        cursor.execute("SELECT COUNT(*) FROM missions WHERE accepted_by = %s AND status = 'completed' AND completed_at >= CURRENT_DATE", (email,))
        daily_completes = cursor.fetchone()[0]
        if daily_completes >= 3:
            return jsonify({"error": "Daily complete limit reached. You can only complete 3 missions per day."}), 429

        # Distance Validation Check
        if req_lat is not None and req_lng is not None:
            cursor.execute("SELECT latitude, longitude FROM missions WHERE id = %s", (mission_id,))
            m_coords = cursor.fetchone()
            if m_coords and m_coords[0] is not None and m_coords[1] is not None:
                dist_deg = ((m_coords[0] - float(req_lat))**2 + (m_coords[1] - float(req_lng))**2) ** 0.5
                if dist_deg > 0.0015: # approx 150 meters leniency
                    return jsonify({"error": "Photo location does not match original mission site! Upload aborted."}), 400

        filename = save_base64_image(after_img_b64)

        cursor.execute(
            """
            UPDATE missions SET status = 'completed', after_image = %s, completed_at = CURRENT_TIMESTAMP
            WHERE id = %s AND accepted_by = %s AND status = 'accepted' RETURNING reward, creator_email
            """,
            (filename, mission_id, email)
        )
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Failed to complete mission. Ensure you are the person who accepted it."}), 400
        
        reward = result[0]
        creator_email = result[1]
        
        # Give reward to user: Points for Self-Report, GeoCoins for Official Missions
        if creator_email == email:
            cursor.execute("UPDATE users SET points = COALESCE(points, 0) + %s WHERE email = %s", (reward, email))
            msg = f"Clean-up verified! Earned {reward} Points (Self-Report)"
        else:
            cursor.execute("UPDATE users SET geocoins = COALESCE(geocoins, 0) + %s WHERE email = %s", (reward, email))
            msg = f"Mission completed! Earned {reward} GeoCoins"
            
        conn.commit()
        return jsonify({"message": msg}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT full_name, geocoins, department FROM users ORDER BY geocoins DESC NULLS LAST LIMIT 50")
        users = [dict(row) for row in cursor.fetchall()]
        return jsonify({"leaderboard": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/user/home", methods=["POST"])
def update_home_location():
    data = request.json
    email = data.get("email")
    home_location = data.get("home_location")
    home_lat = data.get("home_lat")
    home_lng = data.get("home_lng")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE users SET home_location = %s, home_lat = %s, home_lng = %s
            WHERE email = %s
            """,
            (home_location, home_lat, home_lng, email)
        )
        conn.commit()
        return jsonify({"message": "Home location updated successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/notifications/poll", methods=["GET"])
def poll_notifications():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Get user's location
        cursor.execute("SELECT home_lat, home_lng FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user or user['home_lat'] is None or user['home_lng'] is None:
            return jsonify({"notifications": []})
        
        user_lat = user['home_lat']
        user_lng = user['home_lng']

        # Get recent missions (last 10 minutes) not created by this user
        cursor.execute("""
            SELECT id, type, location_text, latitude, longitude, created_at 
            FROM missions 
            WHERE creator_email != %s
            AND created_at >= NOW() - INTERVAL '10 minutes'
            AND status = 'open'
        """, (email,))
        
        recent_missions = cursor.fetchall()
        notifications = []
        for m in recent_missions:
            lat = m['latitude']
            lng = m['longitude']
            if lat and lng:
                # simple euclidian dist for demo: approx 5km is 0.045 deg
                dist_deg = ((lat - user_lat)**2 + (lng - user_lng)**2) ** 0.5
                if dist_deg < 0.045:
                    notifications.append(dict(m))
                    
        return jsonify({"notifications": notifications})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/notifications/verify_poll", methods=["GET"])
def poll_verifications():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT home_lat, home_lng FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user or user['home_lat'] is None or user['home_lng'] is None:
            return jsonify({"verifications": []})
        
        user_lat, user_lng = user['home_lat'], user['home_lng']

        cursor.execute("""
            SELECT id, type, location_text, full_address, latitude, longitude 
            FROM missions 
            WHERE creator_email != %s
            AND verification_status = 'unverified'
            AND status = 'open'
        """, (email,))
        
        unverified = cursor.fetchall()
        verifications = []
        for m in unverified:
            lat, lng = m['latitude'], m['longitude']
            if lat and lng:
                dist_deg = ((lat - user_lat)**2 + (lng - user_lng)**2) ** 0.5
                if dist_deg < 0.045: # approx 5km
                    verifications.append(dict(m))
                    
        return jsonify({"verifications": verifications})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/missions/<int:mission_id>/verify", methods=["POST"])
def verify_mission(mission_id):
    data = request.json
    status = data.get("status") # 'clean' or 'garbage_present'
    email = data.get("email")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if status == 'garbage_present':
            cursor.execute("UPDATE missions SET verification_status = 'verified' WHERE id = %s", (mission_id,))
            msg = "Mission verified as legitimate!"
        else:
            cursor.execute("UPDATE missions SET false_report_count = false_report_count + 1 WHERE id = %s", (mission_id,))
            cursor.execute("SELECT false_report_count FROM missions WHERE id = %s", (mission_id,))
            count = cursor.fetchone()[0]
            if count >= 2:
                # hide mission if false report threshold reached
                cursor.execute("UPDATE missions SET verification_status = 'false_report', status = 'hidden' WHERE id = %s", (mission_id,))
            msg = "False report flagged. Thank you."
            
        conn.commit()
        return jsonify({"message": msg}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/user/<email>", methods=["GET"])
def get_user(email):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT full_name, email, department, geocoins, points, home_location, home_lat, home_lng FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"user": dict(user)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)