import psycopg2
import os

conn = psycopg2.connect(
    host="localhost",
    database="geoclean",
    user="postgres",
    password="likhit@postgres",
    port="5432"
)

cursor = conn.cursor()

try:
    # Create users table first (if not exists)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            department VARCHAR(255),
            geocoins INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            home_location VARCHAR(255),
            home_lat FLOAT,
            home_lng FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Alter users table to add new columns (safe if they already exist)
    cursor.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS geocoins INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS home_location VARCHAR(255),
        ADD COLUMN IF NOT EXISTS home_lat FLOAT,
        ADD COLUMN IF NOT EXISTS home_lng FLOAT;
    """)

    # Create missions table FIRST (must exist before ALTER)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS missions (
            id SERIAL PRIMARY KEY,
            creator_email VARCHAR(255) NOT NULL,
            type VARCHAR(100) NOT NULL,
            description TEXT,
            location_text VARCHAR(255),
            latitude FLOAT,
            longitude FLOAT,
            before_image VARCHAR(255),
            after_image VARCHAR(255),
            status VARCHAR(50) DEFAULT 'open',
            accepted_by VARCHAR(255),
            reward INTEGER DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accepted_at TIMESTAMP,
            completed_at TIMESTAMP,
            full_address TEXT,
            equipment_needed VARCHAR(255),
            people_needed INTEGER DEFAULT 1,
            ai_analysis TEXT,
            verification_status VARCHAR(50) DEFAULT 'unverified',
            false_report_count INTEGER DEFAULT 0
        );
    """)

    # THEN alter missions table to add any missing columns
    cursor.execute("""
        ALTER TABLE missions 
        ADD COLUMN IF NOT EXISTS full_address TEXT,
        ADD COLUMN IF NOT EXISTS equipment_needed VARCHAR(255),
        ADD COLUMN IF NOT EXISTS people_needed INTEGER DEFAULT 1,
        ADD COLUMN IF NOT EXISTS ai_analysis TEXT,
        ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'unverified',
        ADD COLUMN IF NOT EXISTS false_report_count INTEGER DEFAULT 0;
    """)
    
    conn.commit()
    print("Database initialization successful.")
except Exception as e:
    conn.rollback()
    print(f"Error initializing DB: {e}")
finally:
    cursor.close()
    conn.close()

# Create uploads directory if not exists
if not os.path.exists('uploads'):
    os.makedirs('uploads')
    print("Created 'uploads' directory.")
