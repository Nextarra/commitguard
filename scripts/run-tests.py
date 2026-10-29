"""Run owned and independent regression suites, without external execution."""
import sys
import unittest
from pathlib import Path
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
loader=unittest.TestLoader()
suite=unittest.TestSuite([loader.discover(str(root/'tests'),pattern='test_*.py'),loader.discover(str(root/'tests'),pattern='review_*.py')])
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
