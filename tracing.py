"""Manual OpenInference spans for the reference runner's urllib model client."""
from contextlib import contextmanager
import json
import os


def redact(text):
    for key, value in os.environ.items():
        if value and (key.endswith('_API_KEY') or key.endswith('_TOKEN')):
            text = text.replace(value, '[REDACTED]')
    return text


class Telemetry:
    def __init__(self):
        from arize.otel import register
        self.provider = register(space_id=os.environ['ARIZE_SPACE_ID'],
                                 api_key=os.environ['ARIZE_API_KEY'],
                                 project_name='agent-fire-drill', verbose=False)
        self.tracer = self.provider.get_tracer('agent-fire-drill')

    @contextmanager
    def span(self, name, kind, inputs):
        with self.tracer.start_as_current_span(name, record_exception=False,
                                               set_status_on_exception=False) as span:
            span.set_attribute('openinference.span.kind', kind)
            span.set_attribute('input.mime_type', 'application/json')
            span.set_attribute('input.value', redact(json.dumps(inputs)))
            try:
                yield span
            except BaseException as exc:
                # Exception messages from HTTP libraries can contain credentials/headers.
                self.error(span, type(exc).__name__)
                span.add_event('exception', {'exception.type': type(exc).__name__})
                raise

    def output(self, span, value):
        span.set_attribute('output.mime_type', 'application/json')
        span.set_attribute('output.value', redact(json.dumps(value)))

    def error(self, span, message):
        from opentelemetry.trace import Status, StatusCode
        span.set_status(Status(StatusCode.ERROR, redact(message)))

    def close(self):
        try:
            if not self.provider.force_flush(timeout_millis=30000):
                raise RuntimeError('Trace flush timed out')
        finally:
            self.provider.shutdown()
