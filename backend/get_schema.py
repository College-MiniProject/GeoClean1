import psycopg2
try:
    conn = psycopg2.connect(host='localhost', database='geoclean', user='postgres', password='likhit@postgres', port='5432')
    cursor = conn.cursor()
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = cursor.fetchall()
    for table in tables:
        print(f"Table: {table[0]}")
        cursor.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table[0]}'")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]}: {col[1]}")
except Exception as e:
    print(e)
