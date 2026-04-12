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

import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import secrets

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
        password=os.getenv("DB_PASSWORD", "postgres"),
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
    identifier = data.get("email", "")  # Can be email or username
    password = data.get("password", "")

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Check if identifier is an email (contains @) or a username
        if "@" in identifier:
            cursor.execute("SELECT * FROM users WHERE email=%s", (identifier,))
        else:
            cursor.execute("SELECT * FROM users WHERE full_name=%s", (identifier,))

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

# ----- Password Reset Flow -----
@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email", "").strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if not user:
            # Return success even if not found to prevent email enumeration
            return jsonify({"message": "If that email exists, a reset link has been sent."}), 200

        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(hours=1)
        
        cursor.execute(
            "INSERT INTO password_resets (token, email, expires_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (token) DO NOTHING", 
            (token, email, expires)
        )
        conn.commit()

        # Send Email
        reset_link = f"{request.host_url}reset-password.html?token={token}"
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        sender_email = os.getenv("SMTP_EMAIL")
        sender_pass = os.getenv("SMTP_PASSWORD")

        if not sender_email or not sender_pass:
            print(f"DEBUG ONLY (SMTP NOT CONFIGURED): Reset link for {email} -> {reset_link}")
            return jsonify({"message": "If that email exists, a reset link has been sent. Check console logs if testing locally."}), 200

        msg = EmailMessage()
        msg.set_content(f"You requested a password reset for GeoClean.\n\nClick the link below to reset it:\n{reset_link}\n\nThis link expires in 1 hour.")
        msg["Subject"] = "GeoClean Password Reset"
        msg["From"] = sender_email
        msg["To"] = email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_pass)
            server.send_message(msg)

        return jsonify({"message": "If that email exists, a reset link has been sent."}), 200

    except Exception as e:
        print(f"Error sending email: {e}")
        return jsonify({"error": "Failed to process request."}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.json
    token = data.get("token")
    new_password = data.get("new_password")

    if not token or not new_password:
        return jsonify({"error": "Token and new password required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check token validity
        cursor.execute("SELECT email, expires_at FROM password_resets WHERE token=%s", (token,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Invalid or expired token"}), 400
        
        email, expires_at = row[0], row[1]
        
        if datetime.now() > expires_at:
            cursor.execute("DELETE FROM password_resets WHERE token=%s", (token,))
            conn.commit()
            return jsonify({"error": "Token has expired"}), 400

        # Update password
        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute("UPDATE users SET password_hash=%s WHERE email=%s", (hashed_pw, email))
        
        # Delete token
        cursor.execute("DELETE FROM password_resets WHERE email=%s", (email,))
        conn.commit()

        return jsonify({"message": "Password successfully reset. You can now login."}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
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
    if not filename:
        return jsonify({"error": "No image provided. Please capture a photo."}), 400

    # All reports go to admin for review — no AI gating
    ai_analysis = "Pending admin review"

    # People needed: use frontend value if provided, default to 1
    people_needed = data.get("people_needed")
    if people_needed is not None:
        people_needed = max(1, min(int(people_needed), 10))  # Cap between 1-10
    else:
        people_needed = 1

    # Dynamic Reward Scaling based on people needed
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
        # For multi-slot: reset to open and clear all slots
        cursor.execute("""
            UPDATE missions SET status = 'open', accepted_by = NULL, accepted_at = NULL,
            slots_taken = 0, accepted_by_list = '[]'
            WHERE status = 'accepted' AND accepted_at < NOW() - INTERVAL '3 hours'
        """)
        conn.commit()

        cursor.execute("SELECT * FROM missions ORDER BY created_at DESC")
        missions = []
        for row in cursor.fetchall():
            m = dict(row)
            # Parse the accepted_by_list JSON for the frontend
            import json as _json
            try:
                m['accepted_by_list'] = _json.loads(m.get('accepted_by_list') or '[]')
            except Exception:
                m['accepted_by_list'] = []
            m['slots_taken'] = m.get('slots_taken') or 0
            m['slots_available'] = (m.get('people_needed') or 1) - m['slots_taken']
            missions.append(m)
        return jsonify({"missions": missions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/missions/<int:mission_id>/accept", methods=["POST"])
def accept_mission(mission_id):
    import json as _json
    data = request.json
    email = data.get("email")

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Fetch mission details
        cursor.execute("SELECT * FROM missions WHERE id = %s", (mission_id,))
        mission = cursor.fetchone()
        if not mission:
            return jsonify({"error": "Mission not found"}), 404

        if mission['status'] == 'completed':
            return jsonify({"error": "Mission already completed"}), 400

        people_needed = mission['people_needed'] or 1
        slots_taken = mission['slots_taken'] or 0
        accepted_list = _json.loads(mission['accepted_by_list'] or '[]')

        # Check if user already accepted this mission
        if email in accepted_list:
            return jsonify({"error": "You have already accepted this mission"}), 400

        # Check if slots are available
        if slots_taken >= people_needed:
            return jsonify({"error": "All slots for this mission are already taken"}), 400

        # Add user to the accepted list
        accepted_list.append(email)
        new_slots_taken = slots_taken + 1

        # If all slots filled → mark as 'accepted' (fully staffed)
        # If still slots available → keep as 'open' so others can join
        new_status = 'accepted' if new_slots_taken >= people_needed else 'open'

        cursor.execute(
            """
            UPDATE missions SET status = %s, accepted_by = %s, accepted_by_list = %s,
            slots_taken = %s, accepted_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (new_status, email, _json.dumps(accepted_list), new_slots_taken, mission_id)
        )
        conn.commit()

        remaining = people_needed - new_slots_taken
        if remaining > 0:
            msg = f"Slot accepted! {remaining} more worker(s) needed for this mission."
        else:
            msg = "Mission fully staffed! All slots taken. Ready to clean!"

        return jsonify({
            "message": msg,
            "slots_taken": new_slots_taken,
            "slots_available": remaining,
            "people_needed": people_needed,
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/missions/<int:mission_id>/complete", methods=["POST"])
def complete_mission(mission_id):
    import json as _json
    data = request.json
    email = data.get("email")
    after_img_b64 = data.get("after_image")
    req_lat = data.get("latitude")
    req_lng = data.get("longitude")

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Check Daily Complete Cap (Max 3/day)
        cursor.execute("SELECT COUNT(*) FROM missions WHERE accepted_by_list LIKE %s AND status = 'completed' AND completed_at >= CURRENT_DATE", (f'%{email}%',))
        daily_completes = cursor.fetchone()[0]
        if daily_completes >= 3:
            return jsonify({"error": "Daily complete limit reached. You can only complete 3 missions per day."}), 429

        # Verify user is in the accepted list
        cursor.execute("SELECT * FROM missions WHERE id = %s", (mission_id,))
        mission = cursor.fetchone()
        if not mission:
            return jsonify({"error": "Mission not found"}), 404

        accepted_list = _json.loads(mission['accepted_by_list'] or '[]')
        if email not in accepted_list:
            return jsonify({"error": "You have not accepted this mission. Accept it first."}), 400

        if mission['status'] == 'completed':
            return jsonify({"error": "Mission already completed."}), 400

        # Distance Validation Check
        if req_lat is not None and req_lng is not None:
            if mission['latitude'] is not None and mission['longitude'] is not None:
                dist_deg = ((mission['latitude'] - float(req_lat))**2 + (mission['longitude'] - float(req_lng))**2) ** 0.5
                if dist_deg > 0.0015: # approx 150 meters leniency
                    return jsonify({"error": "Photo location does not match original mission site! Upload aborted."}), 400

        filename = save_base64_image(after_img_b64)

        cursor.execute(
            """
            UPDATE missions SET status = 'completed', after_image = %s, completed_at = CURRENT_TIMESTAMP
            WHERE id = %s RETURNING reward, creator_email
            """,
            (filename, mission_id)
        )
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "Failed to complete mission."}), 400
        
        reward = result['reward']
        creator_email = result['creator_email']
        
        # Give reward to ALL accepted users (split or full based on your preference)
        reward_per_person = reward  # Full reward to the completer
        if creator_email == email:
            cursor.execute("UPDATE users SET points = COALESCE(points, 0) + %s WHERE email = %s", (reward_per_person, email))
            msg = f"Clean-up verified! Earned {reward_per_person} Points (Self-Report)"
        else:
            cursor.execute("UPDATE users SET geocoins = COALESCE(geocoins, 0) + %s WHERE email = %s", (reward_per_person, email))
            msg = f"Mission completed! Earned {reward_per_person} GeoCoins"
            
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

# ===================================================================
# ADMIN SYSTEM — Separate login, full control over missions & users
# ===================================================================

@app.route("/admin/login", methods=["POST"])
def admin_login():
    """Admin logs in with credentials from the admins table."""
    data = request.json
    username = data.get("username", "")
    password = data.get("password", "")

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT * FROM admins WHERE username = %s", (username,))
        admin = cursor.fetchone()
        if not admin:
            return jsonify({"error": "Admin not found"}), 404

        if bcrypt.checkpw(password.encode(), admin['password_hash'].encode()):
            return jsonify({
                "message": "Admin login successful",
                "admin": {"id": admin['id'], "username": admin['username'], "role": admin['role']}
            }), 200
        else:
            return jsonify({"error": "Invalid password"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    """Dashboard statistics for the admin panel."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM missions")
        total_missions = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM missions WHERE verification_status = 'unverified'")
        pending = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM missions WHERE verification_status = 'verified'")
        approved = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM missions WHERE verification_status = 'rejected'")
        rejected = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM missions WHERE status = 'completed'")
        completed = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as total FROM missions WHERE verification_status = 'false_report'")
        false_reports = cursor.fetchone()['total']

        return jsonify({
            "total_users": total_users,
            "total_missions": total_missions,
            "pending_review": pending,
            "approved": approved,
            "rejected": rejected,
            "completed": completed,
            "false_reports": false_reports,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/missions", methods=["GET"])
def admin_get_missions():
    """List all missions with optional status filter for admin."""
    status_filter = request.args.get("status")  # 'unverified', 'verified', 'rejected', etc.
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        if status_filter:
            cursor.execute("SELECT * FROM missions WHERE verification_status = %s ORDER BY created_at DESC", (status_filter,))
        else:
            cursor.execute("SELECT * FROM missions ORDER BY created_at DESC")
        import json as _json
        missions = []
        for row in cursor.fetchall():
            m = dict(row)
            try:
                m['accepted_by_list'] = _json.loads(m.get('accepted_by_list') or '[]')
            except Exception:
                m['accepted_by_list'] = []
            missions.append(m)
        return jsonify({"missions": missions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/missions/<int:mission_id>/approve", methods=["POST"])
def admin_approve_mission(mission_id):
    """Admin approves a mission — marks it as verified and visible."""
    data = request.json or {}
    admin_note = data.get("note", "")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE missions SET verification_status = 'verified', ai_analysis = %s WHERE id = %s",
            (f"Admin approved. {admin_note}".strip(), mission_id)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Mission not found"}), 404
        conn.commit()
        return jsonify({"message": f"Mission #{mission_id} approved"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/missions/<int:mission_id>/reject", methods=["POST"])
def admin_reject_mission(mission_id):
    """Admin rejects a mission — hides it from the public feed."""
    data = request.json or {}
    reason = data.get("reason", "Rejected by admin")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE missions SET verification_status = 'rejected', status = 'hidden', ai_analysis = %s WHERE id = %s",
            (reason, mission_id)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Mission not found"}), 404
        conn.commit()
        return jsonify({"message": f"Mission #{mission_id} rejected"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/missions/<int:mission_id>/delete", methods=["DELETE"])
def admin_delete_mission(mission_id):
    """Admin permanently deletes a mission."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM missions WHERE id = %s", (mission_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "Mission not found"}), 404
        conn.commit()
        return jsonify({"message": f"Mission #{mission_id} deleted permanently"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/missions/<int:mission_id>/edit", methods=["PUT"])
def admin_edit_mission(mission_id):
    """Admin can edit any field of a mission."""
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        allowed_fields = ['type', 'description', 'reward', 'people_needed', 'equipment_needed', 'status', 'verification_status']
        updates = []
        values = []
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                values.append(data[field])

        if not updates:
            return jsonify({"error": "No valid fields to update"}), 400

        values.append(mission_id)
        cursor.execute(f"UPDATE missions SET {', '.join(updates)} WHERE id = %s", values)
        if cursor.rowcount == 0:
            return jsonify({"error": "Mission not found"}), 404
        conn.commit()
        return jsonify({"message": f"Mission #{mission_id} updated"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/users", methods=["GET"])
def admin_get_users():
    """List all registered users with their stats."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT id, full_name, email, department, geocoins, points, created_at FROM users ORDER BY created_at DESC")
        users = [dict(row) for row in cursor.fetchall()]
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/users/<int:user_id>/edit", methods=["PUT"])
def admin_edit_user(user_id):
    """Admin can adjust user geocoins, points, etc."""
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        allowed_fields = ['geocoins', 'points', 'department', 'full_name']
        updates = []
        values = []
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                values.append(data[field])

        if not updates:
            return jsonify({"error": "No valid fields to update"}), 400

        values.append(user_id)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", values)
        if cursor.rowcount == 0:
            return jsonify({"error": "User not found"}), 404
        conn.commit()
        return jsonify({"message": "User updated"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/users/<int:user_id>/delete", methods=["DELETE"])
def admin_delete_user(user_id):
    """Admin permanently deletes a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "User not found"}), 404
        conn.commit()
        return jsonify({"message": "User deleted"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)