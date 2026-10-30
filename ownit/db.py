import json
import sqlite3
import threading
import hashlib
import time
from pathlib import Path
from .models import Review, PullRequestGate


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, repo TEXT NOT NULL, sha TEXT NOT NULL, demo INTEGER NOT NULL, completed INTEGER NOT NULL, data TEXT NOT NULL)")
            db.execute('CREATE TABLE IF NOT EXISTS pr_gates (id TEXT PRIMARY KEY, repo TEXT, number INTEGER, sha TEXT, base_sha TEXT, data TEXT, UNIQUE(repo,number,sha,base_sha))')
            db.execute('CREATE TABLE IF NOT EXISTS auth_tokens (token_hash TEXT PRIMARY KEY, kind TEXT, expires REAL, data TEXT)')

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

    def gate(self, id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM pr_gates WHERE id=?', (id,)).fetchone()
        return PullRequestGate.model_validate_json(row[0]) if row else None

    def save_gate(self, gate):
        with self.connect() as db:
            db.execute('INSERT INTO pr_gates VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (gate.id, gate.repo, gate.number, gate.sha, gate.base_sha, gate.model_dump_json()))

    def find_gate(self, repo, number, sha, base):
        with self.connect() as db:
            row = db.execute('SELECT data FROM pr_gates WHERE repo=? AND number=? AND sha=? AND base_sha=?', (repo,number,sha,base)).fetchone()
        return PullRequestGate.model_validate_json(row[0]) if row else None

    def pending_gates(self):
        with self.connect() as db:
            rows = db.execute('SELECT data FROM pr_gates').fetchall()
        return [g for row in rows if (g := PullRequestGate.model_validate_json(row[0])).state in {'queued', 'analyzing'}]

    def gates_for_pr(self, repo, number):
        with self.connect() as db:
            rows = db.execute('SELECT data FROM pr_gates WHERE repo=? AND number=?', (repo,number)).fetchall()
        return [PullRequestGate.model_validate_json(row[0]) for row in rows]

    def put_token(self, token, kind, data, ttl):
        with self.connect() as db:
            db.execute('DELETE FROM auth_tokens WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO auth_tokens VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),kind,time.time()+ttl,json.dumps(data)))

    def read_token(self, token, kind, consume=False):
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock, self.connect() as db:
            row = db.execute('SELECT data FROM auth_tokens WHERE token_hash=? AND kind=? AND expires>?', (key,kind,time.time())).fetchone()
            if consume:
                db.execute('DELETE FROM auth_tokens WHERE token_hash=? AND kind=?', (key,kind))
        return json.loads(row[0]) if row else None
