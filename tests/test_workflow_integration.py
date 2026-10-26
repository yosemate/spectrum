import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class WorkflowIntegrationTests(unittest.TestCase):
    def test_reference_sample_save_and_export(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(root/'tests/workflow_probe.py')],cwd=root,
                                  env=dict(os.environ,QT_QPA_PLATFORM='offscreen',SPECTRUM_LAB_DATA_DIR=directory),
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=65)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertIn('FULL WORKFLOW OK',result.stdout)
