"""Quick setup checks with no provider requests."""
import asyncio
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from agents import Agent, RunContextWrapper
from agents.tool_context import ToolContext
from labagent.evaluate import cases, context_for, prepare
from labagent.model import OpenAIModel
from labagent.policies import Policies, ROOT
from labagent.runner import Runner
from labagent.store import Store
from labagent.types import Clock, Context, ModelError, Runtime
from labagent.utils import SCHEMAS, function_tools, strict_json


class SmokeTests(unittest.TestCase):
    def test_visible_cases_and_world(self):
        number = json.loads((ROOT / "course.json").read_text())["assignment"] or 1
        for case in cases(number):
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as temp:
                store = Store(Path(temp) / "state.sqlite")
                prepare(store, case)
                for session in case["sessions"]:
                    self.assertLessEqual(set(session), {"user", "task"})
                    self.assertTrue(context_for(store, case, session.get("user")).tenant_id)

    def test_local_function_tools_without_network(self):
        async def check(runner):
            agent = Agent(name="Spherelab", tools=function_tools())
            tools = {tool.name: tool for tool in await agent.get_all_tools(RunContextWrapper(context=runner))}
            self.assertEqual(set(tools), set(SCHEMAS))
            self.assertFalse(agent.mcp_servers)
            args = '{"doc_id":"public-notes"}'
            ctx = ToolContext(context=runner, tool_name="read_doc", tool_call_id="local-read", tool_arguments=args)
            value = await tools["read_doc"].on_invoke_tool(ctx, args)
            self.assertIn("instrument", value)
            self.assertEqual(runner.history[-1]["call_id"], "local-read")
            wrong = ToolContext(context=runner, tool_name="send_message", tool_call_id="forged", tool_arguments=args)
            with self.assertRaisesRegex(ModelError, "tool_name_mismatch"):
                await tools["read_doc"].on_invoke_tool(wrong, args)
            self.assertEqual(runner.rt.tool_attempts, 1)

        number = json.loads((ROOT / "course.json").read_text())["assignment"] or 1
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "state.sqlite")
            store.seed()
            rt = Runtime(store, Context("alice", "A", "smoke", ("read_doc",)), number, Clock(), "smoke")
            runner = Runner(rt, Policies(number, "student"), "Read public-notes.")
            with patch.object(socket.socket, "connect", side_effect=AssertionError("tool opened a connection")), \
                 patch.object(socket.socket, "bind", side_effect=AssertionError("tool opened a listener")):
                asyncio.run(check(runner))

    def test_strict_tool_arguments(self):
        for value in ('{"x":0,"x":1}', '{"x":NaN}', '{"x":1e999}', 'not JSON'):
            with self.subTest(value=value), self.assertRaises(ModelError):
                strict_json(value)

    def test_requires_model_credentials(self):
        with patch.dict("os.environ", {"OPENAI_MODEL": "", "OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                OpenAIModel()
