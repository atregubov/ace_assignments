"""Expected to FAIL on an unmodified student starter, then PASS after repair.

Set LAB_ASSIGNMENT and LAB_MODE only in the instructor tree. Student exports fix their assignment.
The visible cases exercise intended effects; passing is not a security proof.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from lab.evaluate import cases, run_case
from lab.policies import ROOT


class PublishedPolicyTests(unittest.TestCase):
    def test_published_security_and_functionality_cases(self):
        config=json.loads((ROOT/'course.json').read_text())
        assignment=config.get('assignment') or int(os.environ.get('LAB_ASSIGNMENT','1'))
        mode=os.environ.get('LAB_MODE','student')
        with tempfile.TemporaryDirectory() as d:
            for c in cases(assignment):
                with self.subTest(case=c['id'], kind=c['kind']):
                    row=run_case(c,mode,Path(d)/c['id'])
                    self.assertEqual(row['status'],'completed')
                    self.assertFalse(row['attacker_objective_met'],'Attacker achieved its fixture objective')
                    if c['kind']=='benign':
                        self.assertTrue(row['task_success'],'Legitimate task must remain possible')


if __name__=='__main__': unittest.main()
