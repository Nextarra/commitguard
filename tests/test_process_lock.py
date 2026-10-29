import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from commitguard.process_lock import acquire_directory_lock


class ProcessLockTests(unittest.TestCase):
    def test_competing_process_excluded_then_allowed_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = 'from pathlib import Path; from commitguard.process_lock import acquire_directory_lock; import sys; h=acquire_directory_lock(Path(sys.argv[1])); h.close()'
            def contender():
                return subprocess.run([sys.executable, '-c', code, tmp], cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True, timeout=5)
            handle = acquire_directory_lock(Path(tmp))
            try:
                result = contender()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('already in use', result.stderr)
            finally:
                handle.close()
            self.assertEqual(contender().returncode, 0)

    def test_crashed_process_releases_lock_without_deleting_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = 'from pathlib import Path; from commitguard.process_lock import acquire_directory_lock; import sys,os; h=acquire_directory_lock(Path(sys.argv[1])); os._exit(7)'
            result = subprocess.run([sys.executable, '-c', code, tmp], cwd=Path(__file__).resolve().parent.parent, timeout=5)
            self.assertEqual(result.returncode, 7)
            with acquire_directory_lock(Path(tmp)):
                self.assertTrue((Path(tmp) / 'server.lock').exists())
