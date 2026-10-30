import json
import sqlite3
import threading
from pathlib import Path
from .models import Review


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, repo TEXT NOT NULL, sha TEXT NOT NULL, demo INTEGER NOT NULL, completed INTEGER NOT NULL, data TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def save(self, review: Review):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?)", (review.id, review.repo, review.sha, review.demo, review.status == 'completed', review.model_dump_json()))

    def get(self, id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM reviews WHERE id=?", (id,)).fetchone()
        return Review.model_validate_json(row[0]) if row else None

    def baseline(self, repo, demo):
        with self.connect() as db:
            row = db.execute("SELECT sha FROM reviews WHERE repo=? AND demo=? AND completed=1 ORDER BY rowid DESC LIMIT 1", (repo, demo)).fetchone()
        return row[0] if row else None

    def history(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM reviews ORDER BY rowid DESC LIMIT 50").fetchall()
        return [{k: v for k, v in json.loads(row[0]).items() if k in {'id', 'repo', 'sha', 'status', 'demo', 'created_at'}} for row in rows]
