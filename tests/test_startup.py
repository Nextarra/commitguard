import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class StartupTests(unittest.TestCase):
    def run_config(self,overrides):
        with tempfile.TemporaryDirectory() as tmp:
            env={**os.environ,'COMMITGUARD_PLANNER':'fixture','COMMITGUARD_PAYMENTS':'fixture','COMMITGUARD_ALLOW_NETWORK':'0','OPENAI_API_KEY':'','OPENAI_MODEL':'','PAYPAL_CLIENT_ID':'','PAYPAL_CLIENT_SECRET':'','PAYPAL_MERCHANT_ID':'',**overrides}
            return subprocess.run([sys.executable,'-m','commitguard.server','--data-dir',tmp],cwd=Path(__file__).resolve().parent.parent,env=env,capture_output=True,text=True,timeout=5)
    def test_external_mode_requires_network_opt_in(self):
        result=self.run_config({'COMMITGUARD_PAYMENTS':'sandbox'});self.assertNotEqual(result.returncode,0);self.assertIn('No network request sent',result.stderr)
    def test_model_credentials_required_before_server_start(self):
        result=self.run_config({'COMMITGUARD_PLANNER':'model','COMMITGUARD_ALLOW_NETWORK':'1'});self.assertNotEqual(result.returncode,0);self.assertIn('No external request sent',result.stderr)
    def test_sandbox_credentials_required_before_server_start(self):
        result=self.run_config({'COMMITGUARD_PAYMENTS':'sandbox','COMMITGUARD_ALLOW_NETWORK':'1'});self.assertNotEqual(result.returncode,0);self.assertIn('No external request sent',result.stderr)

if __name__=='__main__':unittest.main()
