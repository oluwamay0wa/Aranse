import sqlite3
import os

# Dynamically resolve the folder containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "scheduled_posts.db")

def _get_connection():
    """Creates a connection with Write-Ahead Logging enabled to prevent concurrency locks."""
    # Use DB_PATH instead of DB_NAME
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO posts (post_name, content, run_time, image_path) VALUES (?, ?, ?, ?)",
            (post_name, content, run_time, image_path)
        )
        conn.commit()

def get_all_pending_posts():
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, post_name, run_time, content FROM posts WHERE status = 'PENDING' ORDER BY run_time ASC"
        )
        return cursor.fetchall()

def get_pending_posts(current_time: str):
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, content, image_path, retry_count FROM posts WHERE status = 'PENDING' AND run_time <= ?",
            (current_time,)
        )
        return cursor.fetchall()

def get_post_by_id(post_id: int):
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT post_name, content, run_time, image_path FROM posts WHERE id = ?",
            (post_id,)
        )
        return cursor.fetchone()

def update_post(post_id: int, post_name: str, content: str, run_time: str, image_path: str):
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE posts SET post_name = ?, content = ?, run_time = ?, image_path = ?, retry_count = 0 WHERE id = ?",
            (post_name, content, run_time, image_path, post_id)
        )
        conn.commit()

def delete_post(post_id: int):
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()

def mark_published(post_id: int):
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET status = 'PUBLISHED' WHERE id = ?", (post_id,))
        conn.commit()

def mark_failed(post_id: int, error_reason: str):
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET status = ? WHERE id = ?", (error_reason, post_id))
        conn.commit()

def increment_retry(post_id: int):
    """Increments the persistent network retry counter."""
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET retry_count = retry_count + 1 WHERE id = ?", (post_id,))
        conn.commit()