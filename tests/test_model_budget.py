import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from commitguard.model_budget import ModelBudget
from commitguard.policy import PolicyError
from commitguard.adapters import StructuredModelPlanner, RemoteError

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'allowance.sqlite3'
        self.body=json.dumps({'model':'gpt-5.6-terra','max_output_tokens':2048,'reasoning':{'effort':'none'},'service_tier':'default'}).encode()
    def test_concurrent_and_restart_limit(self):
        budget=ModelBudget(self.path)
        def attempt(_):
            try:budget.reserve(self.body);return True
            except PolicyError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt,range(30))),10)
        with self.assertRaises(PolicyError):ModelBudget(self.path).reserve(self.body)
    def test_failed_calls_consume_allowance_without_retry(self):
        calls=[]
        def fail(*args):calls.append(1);raise RemoteError()
        planner=StructuredModelPlanner('fake','gpt-5.6-terra',True,fail,ModelBudget(self.path))
        for _ in range(11):
            with self.assertRaises(PolicyError):planner.propose({'need':'patches','budget_cents':6000})
        self.assertEqual(len(calls),10)
    def test_scope_and_oversize_fail_before_reservation(self):
        budget=ModelBudget(self.path)
        for payload in [self.body.replace(b'gpt-5.6-terra',b'other'), self.body.replace(b'default',b'auto'), self.body[:-1]+b',"input":"'+b'x'*16000+b'"}']:
            with self.assertRaises(PolicyError):budget.reserve(payload)
        for _ in range(10):budget.reserve(self.body)
