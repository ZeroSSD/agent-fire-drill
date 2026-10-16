"""Host-side agent using a Claude model on Amazon Bedrock (Converse API).

Same interface as agent.run_agent, so run_scenario.py can switch providers with LLM_PROVIDER=bedrock.
Tools still run inside the Daytona sandbox through the firedrill CLI. AWS credentials come from the
standard environment variables and are never uploaded or logged.
"""
import json
import os

from agent import SYSTEM, TASK, cli_command
from firedrill.tools import TOOL_SCHEMAS


def to_bedrock_tools(schemas):
    return {'tools': [{'toolSpec': {'name': s['function']['name'],
                                    'description': s['function']['description'],
                                    'inputSchema': {'json': s['function']['parameters']}}}
                      for s in schemas]}


def make_client():
    import boto3
    return boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-west-2'))


def run_agent(sb_exec, guardrail, telemetry, max_turns=8, client=None):
    client = client or make_client()
    model = os.environ['LLM_MODEL']
    messages = [{'role': 'user', 'content': [{'text': TASK}]}]
    count = 0
    for turn in range(max_turns):
        with telemetry.span('bedrock.converse', 'LLM', messages[-1]) as span:
            span.set_attribute('llm.model_name', model)
            span.set_attribute('llm.provider', 'aws')
            response = client.converse(
                modelId=model, messages=messages, system=[{'text': SYSTEM}],
                toolConfig=to_bedrock_tools(TOOL_SCHEMAS), inferenceConfig={'maxTokens': 800})
            usage = response.get('usage', {})
            span.set_attribute('llm.token_count.prompt', usage.get('inputTokens', 0))
            span.set_attribute('llm.token_count.completion', usage.get('outputTokens', 0))
            msg = response['output']['message']
            telemetry.output(span, msg)
        messages.append(msg)
        uses = [block['toolUse'] for block in msg['content'] if 'toolUse' in block]
        if not uses:
            final = ' '.join(block.get('text', '') for block in msg['content']).strip()
            return {'tool_calls': count, 'turns': turn + 1, 'final': final, 'finished': True}
        results = []
        for use in uses:
            with telemetry.span(use['name'], 'TOOL', use['input']) as span:
                command = cli_command(use['name'], use['input'], guardrail)
                out = sb_exec(command)
                parsed = json.loads(out)
                if type(parsed.get('ok')) is not bool:
                    raise ValueError('Malformed CLI output')
                telemetry.output(span, parsed)
                if not parsed['ok']:
                    telemetry.error(span, str(parsed.get('error', 'Tool failure')))
            count += 1
            results.append({'toolResult': {'toolUseId': use['toolUseId'], 'content': [{'text': out}]}})
        messages.append({'role': 'user', 'content': results})
    return {'tool_calls': count, 'turns': max_turns, 'final': '', 'finished': False}
