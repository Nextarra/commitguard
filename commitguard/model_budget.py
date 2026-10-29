"""Durable, conservative allowance for the approved Lenovo model validation."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing
from .policy import require

class ModelBudget:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, reserved_cents INTEGER NOT NULL)')

    def reserve(self, body):
        request = json.loads(body)
        require(request.get('model') == 'gpt-5.6-terra', 'MODEL_SCOPE', 'Only the approved model is enabled.', 503)
        require(len(body) <= 16000 and request.get('max_output_tokens') == 2048 and request.get('reasoning') == {'effort':'none'} and request.get('service_tier') == 'default' and not request.get('tools'), 'MODEL_LIMIT', 'Request exceeds the approved validation limits.', 503)
        # <=16k input bytes plus schema framing, <=2048 output tokens, no tools.
        # At $2/$12 per million tokens, reserve a conservative ten cents/attempt.
        # Failed/uncertain requests retain their full reservation. No retry/refund.
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            count, cents = db.execute('SELECT COUNT(*),COALESCE(SUM(reserved_cents),0) FROM attempts').fetchone()
            require(count < 10 and cents + 10 <= 100, 'MODEL_BUDGET', 'The approved model test allowance is exhausted. No request sent.', 429)
            db.execute('INSERT INTO attempts(reserved_cents) VALUES(10)')
