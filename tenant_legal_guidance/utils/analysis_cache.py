import sqlite3
import os
import json
from threading import Lock

DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/analysis_cache.sqlite')
_cache_lock = Lock()

def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS analysis_cache (
        example_id TEXT PRIMARY KEY,
        data TEXT
    )''')
    return conn

def get_cached_analysis(example_id):
    with _cache_lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute('SELECT data FROM analysis_cache WHERE example_id = ?', (example_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return None

def set_cached_analysis(example_id, data):
    with _cache_lock:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute('REPLACE INTO analysis_cache (example_id, data) VALUES (?, ?)', (example_id, json.dumps(data)))
        conn.commit()
        conn.close() 