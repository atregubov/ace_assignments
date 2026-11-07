"""Direct boundary checks. The supplied vulnerable security policy implementations intentionally fail these tests."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import unittest
from labagent.runner import Runner
from labagent.dispatcher import Dispatcher
from labagent.evaluate import PAYMENT
from labagent.policies import ROOT, Policies
from labagent.store import Store
from labagent.types import Action, BudgetExceeded, Clock, Context, Runtime, PolicyDenied
from labagent.utils import to_canonical_json_string

ASSIGNMENT=json.loads((ROOT/'course.json').read_text()).get('assignment') or int(os.environ.get('LAB_ASSIGNMENT','1'))
MODE=os.environ.get('LAB_MODE','student')


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'state.sqlite'); self.store.seed()
        self.ctx=Context('fin' if ASSIGNMENT==5 else 'alice','A','test',
            ('read_doc','search_docs','send_message','propose_payment','commit_payment','remember','recall','unstable'),
            ('team-a@spherelab.test','collector@external.test'))
        self.rt=Runtime(self.store,self.ctx,ASSIGNMENT,Clock(virtual=True),'boundary')
        self.p=Policies(ASSIGNMENT,MODE)
        self.d=Dispatcher(self.rt,self.p)
        self.a=Action('commit_payment',dict(PAYMENT))
        if ASSIGNMENT==5: self.store.approve(self.ctx,self.a,0,ident='approval-1')

    def tearDown(self): self.tmp.cleanup()

    @unittest.skipUnless(ASSIGNMENT==1,'assignment 1')
    def test_task_contract_cannot_be_changed_by_a_proposal(self):
        ctx=Context('alice','A','summary',('read_doc',),())
        a=Action('send_message',{'recipient':'collector@external.test','body':'unexpected'})
        self.assertFalse(self.p.task_gate.check(ctx,a,self.rt).allowed)
        self.assertTrue(self.p.task_gate.check(self.ctx,Action('read_doc',{'doc_id':'public-notes'}),self.rt).allowed)

    @unittest.skipUnless(ASSIGNMENT==2,'assignment 2')
    def test_authority_defaults_and_revocation(self):
        checks=[('missing',None,Action('read_doc',{'doc_id':'a-notes'})),
                ('unknown',self.ctx,Action('unknown_tool',{})),
                ('alternate_read_path',self.ctx,Action('search_docs',{'query':'CANARY'})),
                ('spoof',self.ctx,Action('read_doc',{'doc_id':'a-notes','role':'admin'})),
                ('project',self.ctx,Action('read_doc',{'doc_id':'a-secret'})),
                ('tenant',self.ctx,Action('read_doc',{'doc_id':'b-notes'}))]
        for label,ctx,a in checks:
            with self.subTest(case=label): self.assertFalse(self.p.authorize.check(ctx,a,self.rt).allowed)
        self.assertTrue(self.p.authorize.check(self.ctx,Action('read_doc',{'doc_id':'a-notes'}),self.rt).allowed)
        user=self.store.get('users','alice'); user['projects']=[]; self.store.put('users',user)
        self.assertFalse(self.p.authorize.check(self.ctx,Action('read_doc',{'doc_id':'a-notes'}),self.rt).allowed)

    @unittest.skipUnless(ASSIGNMENT==3,'assignment 3')
    def test_monotonic_flow_and_fresh_public_run(self):
        self.d.execute(Action('read_doc',{'doc_id':'a-notes'}))
        self.d.execute(Action('read_doc',{'doc_id':'public-notes'}))
        sent=self.d.execute(Action('send_message',{'recipient':'collector@external.test','body':'Public only'}))
        self.assertEqual(sent.get('error'),'policy_denied')
        fresh=Runtime(self.store,self.ctx,3,Clock(virtual=True),'fresh')
        sent=Dispatcher(fresh,self.p).execute(Action('send_message',{'recipient':'collector@external.test','body':'Public only'}))
        self.assertIn('id',sent)

    @unittest.skipUnless(ASSIGNMENT==4,'assignment 4')
    def test_confirmation_must_match_exact_value(self):
        self.store.confirm(self.ctx,'answer_style','bullets','proof')
        row={'user_id':'alice','tenant_id':'A','key':'answer_style','value':'prose',
             'schema_version':1,'status':'candidate','origin':'tool_result','source_id':'public-help','confirmation_id':'proof'}
        self.assertFalse(self.p.memory.check(self.ctx,row,self.rt).allowed)
        row['value']='bullets'
        self.assertTrue(self.p.memory.check(self.ctx,row,self.rt).allowed)

    def payment(self,**changes):
        return self.p.approval.commit(self.ctx,Action('commit_payment',{**PAYMENT,**changes}),self.rt)

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_unchanged(self):
        self.payment(); self.assertEqual(len(self.store.rows('ledger')),1)

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_rejected_review(self):
        self.store.approve(self.ctx,self.a,0,approved=False,ident='approval-1')
        with self.assertRaises(PolicyDenied): self.payment()

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_changed_payee(self):
        with self.assertRaises(PolicyDenied): self.payment(payee='vendor-alt')

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_changed_amount_or_currency(self):
        for changes in [{'amount_cents':7500},{'currency':'EUR'}]:
            with self.subTest(changes=changes),self.assertRaises(PolicyDenied): self.payment(**changes)

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_document_changed(self):
        doc=self.store.get('docs','invoice-a'); doc['body']='new content'; self.store.put('docs',doc)
        with self.assertRaises(PolicyDenied): self.payment()

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_expired(self):
        self.rt.clock.advance(301)
        with self.assertRaises(PolicyDenied): self.payment()

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_role_revoked(self):
        user=self.store.get('users','fin'); user['roles']=[]; self.store.put('users',user)
        with self.assertRaises(PolicyDenied): self.payment()

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_new_operation_replay(self):
        self.payment()
        with self.assertRaises(PolicyDenied): self.payment(operation_id='op-2')

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_concurrent_duplicate(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(lambda _:self.payment(),range(8)))
        self.assertEqual(len({r['id'] for r in receipts}),1)
        self.assertEqual(len(self.store.rows('ledger')),1)

    @unittest.skipUnless(ASSIGNMENT==5,'assignment 5')
    def test_payment_lost_response_retry(self):
        a=self.payment(); b=self.payment()
        self.assertEqual(a,b)
        self.assertEqual(len(self.store.rows('ledger')),1)

    @unittest.skipUnless(ASSIGNMENT==6,'assignment 6')
    def test_late_proposal_and_request_limits(self):
        session = Runner(self.rt, self.p, 'send')
        self.rt.clock.advance(95)
        with self.assertRaises(BudgetExceeded):
            session.execute_tool(Action('send_message', {'recipient':'team-a@spherelab.test','body':'late'}))
        self.assertEqual(self.store.rows('outbox'),[])
        self.assertEqual(self.p.budget.output_limit(self.rt),512)
        self.rt.clock.value=87
        self.assertLessEqual(self.p.budget.timeout(self.rt),3)

    @unittest.skipUnless(ASSIGNMENT==6,'assignment 6')
    def test_tool_budget_and_utf8_bytes(self):
        for _ in range(10): self.d.execute(Action('unstable',{'mode':'normal'}))
        with self.assertRaises(BudgetExceeded): self.d.execute(Action('unstable',{'mode':'normal'}))
        self.rt.result_bytes=16380
        with self.assertRaises(BudgetExceeded): self.p.budget.admit('ééé',self.rt)

    @unittest.skipUnless(ASSIGNMENT==6,'assignment 6')
    def test_audit_required_fields_and_redaction(self):
        self.d.execute(Action('send_message',{'recipient':'team-a@spherelab.test','body':'DUMMY_SENSITIVE_CONTENT'}))
        required={'run_id','event_id','parent_event','principal','tool','argument_digest','decision','outcome','model_attempts','tool_attempts','elapsed','stop_reason'}
        self.assertTrue(required <= self.rt.events[0].keys())
        self.assertNotIn('DUMMY_SENSITIVE_CONTENT',to_canonical_json_string(self.rt.events))


if __name__=='__main__': unittest.main()
