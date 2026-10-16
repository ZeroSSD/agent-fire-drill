import copy
import json
import os
import unittest

import agent_bedrock


class FakeSpan:
    def set_attribute(self, *a):
        pass


class FakeTelemetry:
    def __init__(self):
        self.spans, self.errors = [], []

    def span(self, name, kind, inputs):
        outer = self

        class Ctx:
            def __enter__(self_inner):
                outer.spans.append((name, kind))
                return FakeSpan()

            def __exit__(self_inner, *a):
                return False
        return Ctx()

    def output(self, span, value):
        json.dumps(value)               # must be JSON serializable

    def error(self, span, message):
        self.errors.append(message)


class FakeBedrock:
    """Scripted replies: refund (times out), then the same call again, then a final answer."""
    def __init__(self):
        self.calls = []

    def converse(self, **kw):
        self.calls.append(copy.deepcopy(kw))   # snapshot: the agent keeps appending to its message list
        n = len(self.calls)
        if n == 1:
            blocks = [{'toolUse': {'toolUseId': 't1', 'name': 'refund', 'input': {'order_id': '1001', 'amount': 100}}}]
        elif n == 2:
            blocks = [{'toolUse': {'toolUseId': 't2', 'name': 'get_refund_status', 'input': {'order_id': '1001'}}}]
        else:
            blocks = [{'text': 'done'}]
        return {'output': {'message': {'role': 'assistant', 'content': blocks}}, 'usage': {'inputTokens': 5, 'outputTokens': 7}}


class BedrockAgentTests(unittest.TestCase):
    def setUp(self):
        os.environ['LLM_MODEL'] = 'test-model'

    def test_tool_schemas_translate_to_bedrock_format(self):
        from firedrill.tools import TOOL_SCHEMAS
        cfg = agent_bedrock.to_bedrock_tools(TOOL_SCHEMAS)
        names = [t['toolSpec']['name'] for t in cfg['tools']]
        self.assertEqual(names, ['refund', 'get_refund_status', 'pay'])
        self.assertIn('properties', cfg['tools'][0]['toolSpec']['inputSchema']['json'])

    def test_loop_runs_tools_in_sandbox_and_returns_results_to_model(self):
        commands = []

        def sb_exec(command):
            commands.append(command)
            return json.dumps({'ok': False, 'error': 'ToolTimeout: request timed out'}) if len(commands) == 1 else json.dumps({'ok': True, 'result': {'refunds': []}})
        telemetry, client = FakeTelemetry(), FakeBedrock()
        result = agent_bedrock.run_agent(sb_exec, 'off', telemetry, client=client)
        self.assertTrue(result['finished'])
        self.assertEqual(result['tool_calls'], 2)
        self.assertEqual(len(commands), 2)
        self.assertIn('firedrill.cli', commands[0])
        self.assertEqual(len(telemetry.errors), 1)                      # the timeout is marked as an error span
        # the tool result goes back to the model as a toolResult block with the same id
        last_user = client.calls[1]['messages'][-1]
        self.assertEqual(last_user['content'][0]['toolResult']['toolUseId'], 't1')

    def test_malformed_cli_output_is_rejected(self):
        with self.assertRaises(ValueError):
            agent_bedrock.run_agent(lambda c: json.dumps({'ok': 'maybe'}), 'off', FakeTelemetry(), client=FakeBedrock())


if __name__ == '__main__':
    unittest.main()
