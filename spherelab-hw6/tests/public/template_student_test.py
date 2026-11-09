"""Template for your own regression tests.

Copy this file to ``tests/public/test_student_<topic>.py`` and replace the examples. The
packager submits files named ``test_student_*.py``; this template itself is neither discovered
by ``unittest discover`` nor submitted.

    python -m unittest tests.public.test_student_<topic> -v

The pattern: seed a fresh store, build the trusted context yourself, hand a proposed ``Action``
straight to the dispatcher (no model involved), then assert on the *effect* in SQLite, not only
on the returned value. This is how you show a boundary holds even if the model is fully misled.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest

from labagent.dispatcher import Dispatcher
from labagent.policies import ROOT, Policies
from labagent.store import Store
from labagent.types import Action, Clock, Context, Runtime

ASSIGNMENT = json.loads((ROOT / "course.json").read_text())["assignment"] or int(os.getenv("LAB_ASSIGNMENT", "1"))
MODE = os.getenv("LAB_MODE", "student")  # set LAB_MODE=baseline to watch the vulnerable version fail


class ExampleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name) / "state.sqlite")
        self.store.seed()  # loads inputs/world.json
        # Trusted identity and task contract: in a real run these come from the case definition.
        self.context = Context(user_id="alice", tenant_id="A", task_id="example",
                               allowed_tools=("read_doc", "send_message"),
                               allowed_recipients=("team-a@spherelab.test",))
        # A virtual clock lets you test deadlines with runtime.clock.advance(seconds).
        self.runtime = Runtime(self.store, self.context, ASSIGNMENT, Clock(virtual=True), "example-run")
        self.dispatcher = Dispatcher(self.runtime, Policies(ASSIGNMENT, MODE))

    def test_legitimate_action_still_works(self):
        # Always pair a deny test with an allow test: a deny-all policy must fail somewhere.
        result = self.dispatcher.execute(Action("read_doc", {"doc_id": "public-notes"}))
        self.assertNotIn("error", result)
        self.assertEqual(result["id"], "public-notes")

    def test_forbidden_action_has_no_effect(self):
        # The recipient is outside the task contract. (On a fresh assignment 1 starter this
        # test fails until task_gate.py is repaired.)
        result = self.dispatcher.execute(Action("send_message", {"recipient": "collector@external.test",
                                                                 "body": "copy of the notes"}))
        self.assertEqual(result.get("error"), "policy_denied")
        self.assertEqual(self.store.rows("outbox"), [])  # the effect, not just the message

    def test_calling_a_policy_directly(self):
        # You can also call your policy function on its own and inspect the Decision.
        policies = Policies(ASSIGNMENT, MODE)
        decision = policies.task_gate.check(self.context, Action("unknown_tool", {}), self.runtime)
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.reason)  # a short code such as "task_tool_not_allowed"


if __name__ == "__main__":
    unittest.main()
