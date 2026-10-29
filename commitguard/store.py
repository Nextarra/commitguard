"""Atomic persisted state, trace and fixture ledger. One server process per DB."""
import copy
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

class Store:
    def __init__(self,path):
        self.path=str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False,isolation_level=None)
        os.chmod(path,0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS purchases(id TEXT PRIMARY KEY, owner TEXT NOT NULL, document TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS fixture_orders(id TEXT PRIMARY KEY, document TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, order_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, csrf TEXT NOT NULL);
        ''')
    @contextmanager
    def tx(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
    def save(self,p):
        self.db.execute('INSERT INTO purchases VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document',(p['id'],p['owner'],json.dumps(p)))
    def get(self,id):
        row=self.db.execute('SELECT document FROM purchases WHERE id=?',(id,)).fetchone()
        return json.loads(row[0]) if row else None
    def listing(self,owner=None):
        rows=self.db.execute('SELECT document FROM purchases'+(' WHERE owner=?' if owner else ''),(owner,) if owner else ()).fetchall()
        return [json.loads(row[0]) for row in rows]
    def fixture_get(self,id):
        row=self.db.execute('SELECT document FROM fixture_orders WHERE id=?',(id,)).fetchone()
        return json.loads(row[0]) if row else None
    def fixture_save(self,data):
        self.db.execute('INSERT INTO fixture_orders VALUES(?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document',(data['id'],json.dumps(data)))
    def close(self):
        self.db.close()
