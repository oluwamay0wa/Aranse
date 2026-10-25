import os
import psycopg2
from dotenv import load_dotenv

# Resolve absolute paths and load .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

DB_URL = os.getenv("SUPABASE_DB_URL")

def _get_connection():
    """Creates a connection to the Supabase PostgreSQL pooler."""
    return psycopg2.connect(DB_URL)

def init_db():
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            # Changed AUTOINCREMENT to SERIAL for Postgres
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    post_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    run_time TEXT NOT NULL,
                    image_path TEXT,
                    status TEXT DEFAULT 'PENDING',
                    retry_count INTEGER DEFAULT 0
                )
            ''')
        conn.commit()

def add_post(post_name: str, content: str, run_time: str, image_path: str = ""):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            # Changed SQLite '?' to Postgres '%s'
            cursor.execute(
                "INSERT INTO posts (post_name, content, run_time, image_path) VALUES (%s, %s, %s, %s)",
                (post_name, content, run_time, image_path)
            )
        conn.commit()

def get_all_pending_posts():
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, post_name, run_time, content FROM posts WHERE status = 'PENDING' ORDER BY run_time ASC"
            )
            return cursor.fetchall()

def get_pending_posts(current_time: str):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, content, image_path, retry_count FROM posts WHERE status = 'PENDING' AND run_time <= %s",
                (current_time,)
            )
            return cursor.fetchall()

def get_post_by_id(post_id: int):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT post_name, content, run_time, image_path FROM posts WHERE id = %s",
                (post_id,)
            )
            return cursor.fetchone()

def update_post(post_id: int, post_name: str, content: str, run_time: str, image_path: str):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE posts SET post_name = %s, content = %s, run_time = %s, image_path = %s, retry_count = 0 WHERE id = %s",
                (post_name, content, run_time, image_path, post_id)
            )
        conn.commit()

def delete_post(post_id: int):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM posts WHERE id = %s", (post_id,))
        conn.commit()

def mark_published(post_id: int):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE posts SET status = 'PUBLISHED' WHERE id = %s", (post_id,))
        conn.commit()

def mark_failed(post_id: int, error_reason: str):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE posts SET status = %s WHERE id = %s", (error_reason, post_id))
        conn.commit()

def increment_retry(post_id: int):
    with _get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE posts SET retry_count = retry_count + 1 WHERE id = %s", (post_id,))
        conn.commit()