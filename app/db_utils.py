import psycopg2
from app.config import DB_CONFIG

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def set_user_id_in_session(conn, user_id):
    cur = conn.cursor()
    cur.execute("SET myapp.user_id = %s;", (user_id,))
    cur.close()