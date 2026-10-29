"""Local fixture QA ONLY: drop HTTP replies after completed simulated capture.

Never imports sandbox/model adapters or reads credential configuration.
"""
import argparse
from pathlib import Path
import socket
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from commitguard.adapters import FixturePlanner, FixturePayPal
from commitguard.process_lock import acquire_directory_lock
from commitguard.server import make_handler
from commitguard.service import Service
from commitguard.store import Store

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8878)
parser.add_argument('--data-dir', type=Path, required=True)
parser.add_argument('--drop-followup-read', action='store_true')
args = parser.parse_args()
args.data_dir.mkdir(parents=True, exist_ok=True)
lock = acquire_directory_lock(args.data_dir)
store = Store(args.data_dir / 'commitguard.sqlite3')
service = Service(store, FixturePlanner(), FixturePayPal(store), f'http://127.0.0.1:{args.port}')
pending_read_drop = threading.Event()
Base = make_handler(service, args.port)


class FaultHandler(Base):
    def send(self, status, data, content_type='application/json', cookie=None):
        capture_reply = self.command == 'POST' and self.path == '/api/capture' and status == 200 and data.get('state') == 'COMPLETED'
        read_reply = self.command == 'GET' and self.path.startswith('/api/purchases/') and pending_read_drop.is_set()
        if capture_reply or read_reply:
            if capture_reply and args.drop_followup_read:
                pending_read_drop.set()
            if read_reply:
                pending_read_drop.clear()
            # The underlying handler has already committed its state; only the
            # HTTP reply is lost. Never retry or invoke another capture.
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        super().send(status, data, content_type, cookie)


server = ThreadingHTTPServer(('127.0.0.1', args.port), FaultHandler)
server.daemon_threads = True
print(f'Fixture-only HTTP response fault server: http://127.0.0.1:{args.port}', flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
    store.close()
    lock.close()
