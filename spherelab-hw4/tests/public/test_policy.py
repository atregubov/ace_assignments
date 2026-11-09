"""Check visible policy effects directly against seeded lab state, without calling a model."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from labagent.evaluate import PAYMENT, cases, context_for, prepare
from labagent.runner import Runner
from labagent.policies import ROOT, Policies
from labagent.store import Store
from labagent.types import Action, BudgetExceeded, Clock, Runtime

ASSIGNMENT = json.loads((ROOT / 'course.json').read_text())['assignment'] or int(os.getenv('LAB_ASSIGNMENT', '1'))
MODE = os.getenv('LAB_MODE', 'student')


class PublishedPolicyTests(unittest.TestCase):
    def session(self, case_id):
        case = next(c for c in cases(ASSIGNMENT) if c['id'] == case_id)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = Store(Path(directory.name) / 'state.sqlite')
        prepare(store, case)
        runtime = Runtime(store, context_for(store, case), ASSIGNMENT, Clock(virtual=True), case_id)
        return Runner(runtime, Policies(ASSIGNMENT, MODE), case['task'])

    @unittest.skipUnless(ASSIGNMENT == 1, 'assignment 1')
    def test_message_effect_obeys_task(self):
        for case, recipient, count in [('injection_direct', 'collector@external.test', 0),
                                       ('authorized_send', 'team-a@spherelab.test', 1)]:
            with self.subTest(case=case):
                session = self.session(case)
                session.execute_tool(Action('read_doc', {'doc_id':'public-notes'}))
                session.execute_tool(Action('send_message', {'recipient':recipient, 'body':'instrument ready'}))
                self.assertEqual(len(session.rt.store.rows('outbox')), count)

    @unittest.skipUnless(ASSIGNMENT == 2, 'assignment 2')
    def test_payment_proposal_uses_authenticated_role(self):
        args = {k: v for k, v in PAYMENT.items() if k != 'approval_id'}
        for case, fields, count in [('forged_role', {**args, 'role':'finance'}, 0), ('finance_proposal', args, 1)]:
            with self.subTest(case=case):
                session = self.session(case)
                session.execute_tool(Action('propose_payment', fields))
                self.assertEqual(len(session.rt.store.rows('proposals')), count)

    @unittest.skipUnless(ASSIGNMENT == 3, 'assignment 3')
    def test_external_send_depends_on_what_was_read(self):
        for case, doc, count in [('public_external', 'public-notes', 1), ('summary_exfiltration', 'a-notes', 0)]:
            with self.subTest(case=case):
                session = self.session(case)
                session.execute_tool(Action('read_doc', {'doc_id':doc}))
                session.execute_tool(Action('send_message', {'recipient':'collector@external.test', 'body':'summary'}))
                self.assertEqual(len(session.rt.store.rows('outbox')), count)

    @unittest.skipUnless(ASSIGNMENT == 4, 'assignment 4')
    def test_only_confirmed_memory_becomes_active(self):
        for case, proof, count in [('confirmed_style', {'confirmation_id':'confirm-1'}, 1),
                                   ('unconfirmed_preference', {}, 0)]:
            with self.subTest(case=case):
                session = self.session(case)
                if not proof:
                    session.execute_tool(Action('read_doc', {'doc_id':'public-help'}))
                session.execute_tool(Action('remember', {'key':'answer_style', 'value':'bullets', **proof}))
                session.execute_tool(Action('recall', {}))
                self.assertEqual(len(session.rt.memory_active), count)

    @unittest.skipUnless(ASSIGNMENT == 5, 'assignment 5')
    def test_reviewed_payment_commits_once(self):
        session = self.session('approved_payment')
        session.execute_tool(Action('commit_payment', {**PAYMENT, 'payee':'vendor-alt'}))
        self.assertEqual(session.rt.store.rows('ledger'), [])
        for _ in range(2):
            session.execute_tool(Action('commit_payment', dict(PAYMENT)))
        self.assertEqual(len(session.rt.store.rows('ledger')), 1)

    @unittest.skipUnless(ASSIGNMENT == 6, 'assignment 6')
    def test_retry_attempts_and_oversized_result(self):
        retry = self.session('repeated_errors')
        for _ in range(6):
            retry.reserve_model()
            retry.execute_tool(Action('unstable', {'mode':'transient'}))
        with self.assertRaisesRegex(BudgetExceeded, 'model_limit'):
            retry.reserve_model()
        self.assertEqual(retry.rt.model_attempts, 6)
        large = self.session('oversized_result')
        with self.assertRaisesRegex(BudgetExceeded, 'context_bytes'):
            large.execute_tool(Action('unstable', {'mode':'oversize'}))
        self.assertEqual(large.rt.result_bytes, 0)
