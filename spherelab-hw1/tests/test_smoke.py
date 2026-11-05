import json
from pathlib import Path
import tempfile
import unittest
from agent.model_adapter import parse_json, converse_request, parse_converse
from lab.types import ModelError
from lab.evaluate import cases, run_case
from lab.policies import ROOT


class SmokeTests(unittest.TestCase):
    def test_benign_run_without_dependencies(self):
        assignment = json.loads((ROOT/'course.json').read_text()).get('assignment') or 1
        c = next(c for c in cases(assignment) if c['kind'] == 'benign')
        with tempfile.TemporaryDirectory() as d:
            row = run_case(c, 'student', Path(d)/'case')
            self.assertEqual(row['status'], 'completed')
            self.assertTrue(row['task_success'])
            self.assertEqual(row['evidence_kind'], 'scripted_simulation')
            self.assertIsNone(row['input_tokens'])

    def test_strict_model_envelopes(self):
        for bad in ['```json\n{}\n```', '{"tool":"read_doc","tool":"send_message","args":{}}',
                    '{"final":1}', '{"tool":"read_doc","args":{},"role":"admin"}',
                    '{"tool":"read_doc","args":{"x":NaN}}', '[{"final":"x"}]']:
            with self.subTest(bad=bad), self.assertRaises(ModelError):
                parse_json(bad)
        self.assertEqual(parse_json('{"final":"done"}').final, 'done')

    def test_native_tool_cycle_schema(self):
        history = [{'role':'user','content':'Read public-notes'},
                   {'action':{'tool':'read_doc','args':{'doc_id':'public-notes'}},'call_id':'call_1'},
                   {'result':{'body':'ok'},'wrapped':{'untrusted_tool_data':{'body':'ok'}},'call_id':'call_1'}]
        req = converse_request('model', 'system', history, 512, 'native')
        self.assertEqual(req['messages'][2]['content'][0]['toolResult']['toolUseId'], 'call_1')
        reply = parse_converse({'output':{'message':{'content':[{'toolUse':{
            'name':'read_doc','input':{'doc_id':'public-notes'},'toolUseId':'call_1'}}]}},
            'usage':{'inputTokens':10,'outputTokens':4}}, 'native')
        self.assertEqual(reply.action.tool, 'read_doc')
        self.assertEqual(reply.output_tokens, 4)

    def test_multiple_native_calls_are_not_executed(self):
        call={'toolUse':{'name':'read_doc','input':{},'toolUseId':'a'}}
        with self.assertRaises(ModelError):
            parse_converse({'output':{'message':{'content':[call,call]}}},'native')


if __name__ == '__main__': unittest.main()
