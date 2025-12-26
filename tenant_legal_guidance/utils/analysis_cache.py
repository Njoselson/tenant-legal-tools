import json
import os
import sqlite3
from threading import Lock

DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/analysis_cache.sqlite")
_cache_lock = Lock()


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_cache (
        example_id TEXT PRIMARY KEY,
        data TEXT,
        expires_at TEXT,
        created_at TEXT
    )"""
    )
    # Add expires_at and created_at columns if they don't exist (migration)
    try:
        conn.execute("ALTER TABLE analysis_cache ADD COLUMN expires_at TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE analysis_cache ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    return conn


def get_cached_analysis(example_id):
    from datetime import datetime

    with _cache_lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT data, expires_at FROM analysis_cache WHERE example_id = ?",
            (example_id,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            data_str, expires_at_str = row[0], row[1] if len(row) > 1 else None

            # Check expiration if expires_at is set
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.utcnow() > expires_at:
                        # Entry expired, return None
                        return None
                except (ValueError, TypeError):
                    # Invalid expiration format, return data anyway
                    pass

            return json.loads(data_str)
        return None


def set_cached_analysis(example_id, data, expires_at=None, created_at=None):
    from datetime import datetime

    with _cache_lock:
        conn = _get_conn()
        cur = conn.cursor()

        # If data is a dict with expires_at/created_at, extract them
        expires_at_str = None
        created_at_str = None
        data_to_store = data

        if isinstance(data, dict):
            expires_at_str = data.get("expires_at") or (
                expires_at.isoformat() if expires_at else None
            )
            created_at_str = data.get("created_at") or (
                created_at.isoformat() if created_at else datetime.utcnow().isoformat()
            )
            data_to_store = data.get("data", data)

        if not created_at_str:
            created_at_str = datetime.utcnow().isoformat()

        cur.execute(
            "REPLACE INTO analysis_cache (example_id, data, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (example_id, json.dumps(data_to_store), expires_at_str, created_at_str),
        )
        conn.commit()
        conn.close()
