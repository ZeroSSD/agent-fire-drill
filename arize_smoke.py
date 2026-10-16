"""Send a labeled setup span only; no model, sandbox, payment, or safety verdict."""
import os
import sys

from tracing import Telemetry


def main():
    missing = [name for name in ('ARIZE_API_KEY', 'ARIZE_SPACE_ID') if not os.environ.get(name)]
    if missing:
        print('Missing environment variables: ' + ', '.join(missing), file=sys.stderr)
        return 1
    telemetry = None
    try:
        telemetry = Telemetry()
        with telemetry.span('arize_setup_check', 'CHAIN', {'source': 'setup_check'}) as span:
            span.set_attribute('metadata', '{"source":"setup_check","synthetic":true}')
            telemetry.output(span, {'message': 'Arize connectivity check only'})
            trace_id = f'{span.get_span_context().trace_id:032x}'
        telemetry.close()
        telemetry = None
        print('Setup span export attempted. Project: agent-fire-drill')
        print('Trace ID: ' + trace_id)
        print('Open Arize and find this trace to confirm hosted arrival.')
        print('This is a setup check, not a payment experiment result.')
        return 0
    except Exception as exc:
        print(f'Arize check failed ({type(exc).__name__}); hosted arrival unconfirmed.', file=sys.stderr)
        return 1
    finally:
        if telemetry is not None:
            try:
                telemetry.close()
            except Exception:
                print('Trace shutdown failed.', file=sys.stderr)


if __name__ == '__main__':
    raise SystemExit(main())
