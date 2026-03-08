import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="geoclean",
    user="postgres",
    password="likhit@postgres",
    port="5432"
)

print("Database connected successfully!")

conn.close()