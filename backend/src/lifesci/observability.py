"""Optional structured observations. No model reasoning or record content by default."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import json
from time import monotonic
from uuid import uuid4

from .ids import iso, utc_now

_correlation = ContextVar('lifesci_observation', default={})


class Telemetry:
    def __init__(self, sink=None, *, langfuse=None, capture_content=False):
        self.sink, self.langfuse, self.capture_content = sink, langfuse, capture_content
        self.errors = []
        self.refs = []

    @classmethod
    def from_env(cls):
        import os
        if os.environ.get('LIFESCI_TELEMETRY') != 'langfuse':
            return cls()
        telemetry = cls()
        try:
            from langfuse import Langfuse
            telemetry.langfuse = Langfuse()
        except Exception as exc:
            telemetry.errors.append({'operation': 'langfuse_configuration', 'error_type': type(exc).__name__})
        return telemetry

    def correlation(self):
        return dict(_correlation.get())

    def emit(self, event):
        if self.sink:
            try:
                self.sink(event)
            except Exception as exc:
                self.errors.append({'operation': 'local_export', 'error_type': type(exc).__name__})

    @contextmanager
    def observation(self, name, *, metadata=None, input=None, trace_context=None):
        context = {**_correlation.get(), **{k: v for k, v in (metadata or {}).items() if v is not None}}
        local_id = uuid4().hex
        event = {'name': name, 'local_observation_id': local_id,
                 'parent_local_id': context.get('local_observation_id'), **context,
                 'started_at': iso(utc_now()), 'status': 'completed'}
        context['local_observation_id'] = local_id
        token = _correlation.set(context)
        started = monotonic()
        span = None
        stack = ExitStack()
        try:
            if self.langfuse:
                try:
                    from langfuse import propagate_attributes
                    span = stack.enter_context(self.langfuse.start_as_current_observation(
                        name=name, as_type='span', metadata=context,
                        input=input if self.capture_content else None,
                        **({'trace_context': trace_context} if trace_context else {})))
                    stack.enter_context(propagate_attributes(
                        session_id=context.get('session_id'),
                        metadata={k: str(v) for k, v in context.items() if v is not None}))
                    event.update(trace_id=span.trace_id, observation_id=span.id,
                                 trace_url=self.langfuse.get_trace_url(trace_id=span.trace_id))
                    self.refs.append({k: event[k] for k in ('trace_id', 'observation_id', 'trace_url')})
                    context['trace_context'] = {'trace_id': span.trace_id, 'parent_span_id': span.id}
                except Exception as exc:
                    self.errors.append({'operation': 'langfuse_start', 'error_type': type(exc).__name__})
            if self.capture_content and input is not None:
                event['input'] = input
            yield event
        except BaseException as exc:
            event.update(status='error', error_type=type(exc).__name__)
            raise
        finally:
            event['finished_at'] = iso(utc_now())
            event['elapsed_seconds'] = monotonic() - started
            if span:
                try:
                    span.update(output=event.get('output') if self.capture_content else None,
                                metadata={**context, 'status': event['status']})
                except Exception as exc:
                    self.errors.append({'operation': 'langfuse_update', 'error_type': type(exc).__name__})
            try:
                stack.close()
            except Exception as exc:
                self.errors.append({'operation': 'langfuse_end', 'error_type': type(exc).__name__})
            _correlation.reset(token)
            if not self.capture_content:
                event.pop('input', None)
                event.pop('output', None)
            self.emit(event)

    def score(self, name, value, *, trace_id, comment=''):
        if not self.langfuse:
            return False
        try:
            self.langfuse.create_score(name=name, value=value, trace_id=trace_id,
                                       data_type='NUMERIC', comment=comment)
            return True
        except Exception as exc:
            self.errors.append({'operation': 'score_sync', 'error_type': type(exc).__name__})
            return False

    def flush(self):
        if self.langfuse:
            try:
                self.langfuse.flush()
            except Exception as exc:
                self.errors.append({'operation': 'langfuse_flush', 'error_type': type(exc).__name__})


def instrument_turn(method):
    """Restore queued correlation for local or replacement/background workers."""
    from functools import wraps
    @wraps(method)
    def wrapped(self, ctx, thread_id, turn_id):
        thread = self._thread(ctx, thread_id).state
        turn = self.p.store.read().require(ctx.tenant_id, 'engineering_chat_turn', turn_id).state
        with self.p.telemetry.observation('assistant.turn', metadata={
            'mission_id': thread['mission_id'], 'session_id': thread_id, 'turn_id': turn_id,
            'tenant_id': ctx.tenant_id, 'site_id': thread['site_id'],
            'event_ids': turn.get('background_event_ids', []),
            'trigger_kind': turn.get('origin', 'user_turn')},
            trace_context=turn.get('_trace_context')) as observed:
            result = method(self, ctx, thread_id, turn_id)
            observed['output'] = {'status': result['turns'][-1]['status'],
                                  'artifacts': result['turns'][-1]['artifacts']}
            return result
    return wrapped


def instrument_tool(name):
    from functools import wraps
    def decorate(method):
        @wraps(method)
        def wrapped(ctx, raw):
            # The closure's host is deliberately attached by the caller.
            telemetry = wrapped.telemetry
            arguments = {k: v for k, v in raw.items() if not k.startswith('_')}
            with telemetry.observation('tool.call', metadata={'tool_name': name}, input=arguments) as event:
                result = method(ctx, raw)
                event['output'] = result
                return result
        return wrapped
    return decorate


def instrument_retrieval(method):
    from functools import wraps
    @wraps(method)
    def wrapped(self, ctx, thread, **kwargs):
        with self.p.telemetry.observation('workspace.' + method.__name__, metadata={
            'mission_id': thread['mission_id'], 'session_id': thread['id'],
            'tenant_id': ctx.tenant_id, 'site_id': thread['site_id']}, input=kwargs) as event:
            result = method(self, ctx, thread, **kwargs)
            event['output'] = result
            return result
    return wrapped


def instrument_gateway(method):
    from functools import wraps
    @wraps(method)
    def wrapped(self, request):
        telemetry = getattr(self, 'telemetry', None)
        if telemetry is None:
            return method(self, request)
        with telemetry.observation('model.gateway', metadata={
            'mission_id': request.mission_id, 'task_kind': request.task_kind,
            'prompt_version': request.prompt_version, 'tenant_id': request.ctx.tenant_id}) as event:
            result = method(self, request)
            event['output'] = {'run_id': result.run_id, 'status': result.status, 'route': result.route,
                               'cost_estimate_usd': result.cost_usd, 'attempt_count': len(result.attempts)}
            return result
    return wrapped
