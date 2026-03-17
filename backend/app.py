import webbrowser
from dotenv import load_dotenv
import os
import webbrowser
from flask import Flask, request, jsonify
import psycopg2
import bcrypt
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

load_dotenv()

# database connection
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=os.getenv("DB_PORT")
)

cursor = conn.cursor()

@app.route("/")
def home():
    return "GeoClean backend is running"

@app.route("/register", methods=["POST"])
def register():

    data = request.json

    full_name = data["full_name"]
    email = data["email"]
    password = data["password"]
    department = data["department"]

    # hash password
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

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

@app.route("/login", methods=["POST"])
def login():
    data = request.json

    email = data["email"]
    password = data["password"]

    cursor.execute(
        "SELECT password_hash FROM users WHERE email=%s",
        (email,)
    )

    user = cursor.fetchone()

    if user is None:
        return jsonify({"error": "User not found"}), 404

    stored_hash = user[0]

    if bcrypt.checkpw(password.encode(), stored_hash.encode()):
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid password"}), 401

if __name__ == "__main__":
    webbrowser.open("http://127.0.0.1:5500/index.html")
    app.run(debug=True, use_reloader=False)