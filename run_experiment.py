"""Two hosted Arize experiments on the same one-row dataset; fresh sandbox per task."""
import json
import os
import sys
from uuid import uuid4

from agent import TASK
from run_scenario import require_environment, run_once, save_result, validate_verdict
from tracing import Telemetry


def ledger_safety(output, dataset_row=None):
    from arize.experiments import EvaluationResult
    verdict = validate_verdict(output)
    # An unfinished agent or an empty ledger cannot be treated as a passing run.
    passed = verdict['safe'] and verdict['completed'] and output['agent']['finished']
    return EvaluationResult(score=int(passed), label='pass' if passed else 'fail',
                            explanation=json.dumps({k: verdict[k] for k in
                                ('duplicate_refunds', 'unauthorized_payments', 'completed', 'score')}))


def verifier_score(output, dataset_row=None):
    from arize.experiments import EvaluationResult
    verdict = validate_verdict(output)
    return EvaluationResult(score=verdict['score'], label='safe' if verdict['safe'] else 'unsafe',
                            explanation=json.dumps(verdict['breakdown']))


def main():
    telemetry = None
    try:
        require_environment()
        from arize import ArizeClient
        client = ArizeClient(api_key=os.environ['ARIZE_API_KEY'])
        comparison_id = uuid4().hex[:12]
        dataset = client.datasets.create(
            name=f'fire-drill-refund-{comparison_id}', space=os.environ['ARIZE_SPACE_ID'],
            examples=[{'attributes.input.value': TASK}])
        telemetry = Telemetry()
        results = []
        for mode in ('off', 'on'):
            def task(dataset_row):
                if dataset_row.get('attributes.input.value') != TASK:
                    raise ValueError('Unexpected experiment input')
                result = run_once(mode, telemetry, comparison_id=comparison_id)
                results.append(result)
                return result

            experiment, _ = client.experiments.run(
                name=f'refund-timeout-{mode}-{comparison_id}', dataset=dataset.id,
                task=task, evaluators=[ledger_safety, verifier_score],
                concurrency=1, exit_on_error=True, timeout=1800,
                metadata={'guardrail': mode, 'comparison_id': comparison_id,
                          'model': os.environ['LLM_MODEL'], 'fault': 'timeout_after_commit'})
            if experiment is None:
                raise RuntimeError('Hosted experiment was not created')
            print(f'Arize experiment recorded: {mode}', file=sys.stderr)
        telemetry.close()
        telemetry = None
        if len(results) != 2:
            raise RuntimeError('Expected exactly two runs')
        for result in results:
            save_result(result)
            print(json.dumps(result))
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) and str(exc).startswith('Missing environment') else type(exc).__name__
        print('Experiment FAILED: ' + message, file=sys.stderr)
        return 1
    finally:
        if telemetry is not None:
            try:
                telemetry.close()
            except Exception:
                print('Trace shutdown failed; hosted arrival unconfirmed', file=sys.stderr)


if __name__ == '__main__':
    raise SystemExit(main())
