"""Opt-in timing of assistant turns with real Modal inference: where the seconds of one answer go.

Uses an isolated in-memory store and a synthetic demo workspace, never the production database, and
the same loop the demo workspaces use. Provider calls are capped. Prints, per turn, the wall time and
its split into model calls and record lookups, and per model call its latency, prompt size, output
tokens and what it asked for. Hosted compute billing is not reported.

    ../.venv/bin/python scripts/time_assistant_turns.py --execute --output /tmp/fresh-dir
"""
from pathlib import Path
from time import perf_counter
import argparse
import json
import os
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))

from src.lifesci.container import Platform
from src.lifesci.demo_scenarios import PERSONAS, SCENARIOS
from src.lifesci.envfile import parse_env
from src.lifesci.gateway.providers import ModalProvider, ProviderError
from src.lifesci.store import RecordStore

DEFAULT = ('pe-compare', 'pe-do-drop')


class TimedModal(ModalProvider):
    """Records every request's duration and token counts; refuses once the cap is reached."""

    def __init__(self, settings, limit):
        super().__init__(environ=settings)
        self.limit = limit
        self.posts = []
        self.extra = {}   # extra request fields for an experiment, e.g. turning the model's thinking off

    def _post(self, path, body, headers, timeout_s):
        if len(self.posts) >= self.limit:
            raise ProviderError('Timing run provider-call limit reached', retryable=False)
        entry = {'started': perf_counter(), 'prompt_chars': len(json.dumps(body.get('messages'))),
                 'tool_schema_chars': len(json.dumps(body.get('tools') or [])), 'messages': len(body.get('messages') or []),
                 'tools_offered': len(body.get('tools') or []), 'status': 'started'}
        self.posts.append(entry)
        if self.extra:
            body = {**body, **self.extra}
        try:
            response = super()._post(path, body, headers, timeout_s)
        except ProviderError as exc:
            entry.update(status=f'failed: {exc.kind}', seconds=round(perf_counter() - entry.pop('started'), 2))
            raise
        usage = response.get('usage') or {}
        message = ((response.get('choices') or [{}])[0].get('message') or {})
        details = usage.get('completion_tokens_details') or {}
        entry.update(status='returned', seconds=round(perf_counter() - entry.pop('started'), 2),
                     prompt_tokens=usage.get('prompt_tokens'), completion_tokens=usage.get('completion_tokens'),
                     cached_tokens=(usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
                     reasoning_tokens=details.get('reasoning_tokens'),
                     # Reasoning text is counted, never kept: only its length shows where output tokens went.
                     reasoning_chars=len(message.get('reasoning_content') or message.get('reasoning') or ''),
                     answer_chars=len(message.get('content') or ''),
                     tool_calls=[(c.get('function') or {}).get('name') for c in message.get('tool_calls') or []])
        return response


def seconds_between(start, end):
    from datetime import datetime
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() if start and end else 0.


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--execute', action='store_true', help='Explicitly allow real provider requests')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenarios', default=','.join(DEFAULT), help='Comma-separated demo scenario ids')
    parser.add_argument('--prompt', action='append', default=[], help='An extra question to time, as the process engineer')
    parser.add_argument('--calls', type=int, default=30, help='Most provider requests across the whole run')
    parser.add_argument('--request-json', default='', help='Experiment: JSON object merged into every provider request body')
    args = parser.parse_args()
    if not args.execute:
        parser.error('No inference without --execute')
    output = args.output.resolve()
    if output.exists():
        parser.error('Use a fresh output directory; previous evidence is never overwritten')
    wanted = [s for s in args.scenarios.split(',') if s]
    by_id = {s['scenario_id']: s for s in SCENARIOS}
    if unknown := [s for s in wanted if s not in by_id]:
        parser.error(f'Unknown scenario {unknown[0]}; choose from {", ".join(by_id)}')
    settings = {}
    for path in (REPO / 'backend/deploy/aws/production.env', REPO / 'backend/.env.local'):
        if path.is_file():
            settings.update(parse_env(path.read_text()))
    settings.update(os.environ)
    # Explicit configuration only: no accidental production database or alternate model.
    os.environ['LIFESCI_LLM_PROVIDER'] = 'modal'
    os.environ['LIFESCI_LLM_MODEL'] = settings.get('LIFESCI_LLM_MODEL') or 'zai-org/GLM-5.3'
    os.environ['ASSISTANT_LOOP'] = 'tools'
    for name in ('LIFESCI_INTERPRETER_MODEL', 'LIFESCI_INTERPRETER_PROVIDER', 'LIFESCI_DATABASE_URL'):
        os.environ.pop(name, None)
    provider = TimedModal(settings, limit=args.calls)
    provider.extra = json.loads(args.request_json) if args.request_json else {}
    provider._check_configuration()
    platform = Platform(RecordStore(), providers={'modal': provider}, allow_unqualified=True)
    platform.gateway.max_retries = 0

    questions = [(by_id[s]['persona'], s, by_id[s]['prompt']) for s in wanted] + [('process_engineer', f'prompt-{i + 1}', p) for i, p in enumerate(args.prompt)]
    workspaces, turns = {}, []
    for persona, label, prompt in questions:
        assert persona in PERSONAS
        if persona not in workspaces:
            visitor = f'anon-timing-{persona}'
            tenant = platform.demo.provision(visitor, persona, True)['tenant_id']
            workspaces[persona] = platform.identity.context_for(tenant, visitor)
        ctx = workspaces[persona]
        thread = platform.engineering_conversations.create(ctx, {'site_id': 'NF1'})
        first = len(provider.posts)
        started = perf_counter()
        queued = platform.engineering_conversations.enqueue(ctx, thread['id'], {'text': prompt, 'expected_revision': thread['revision']})
        try:
            result = platform.engineering_conversations.run_turn(ctx, thread['id'], queued['turn_ids'][-1])
            turn = result['turns'][-1]
        except Exception as exc:  # a failed turn is a timing result too
            turn = {'status': f'error: {type(exc).__name__}: {str(exc)[:200]}', 'tool_steps': [], 'reply': None}
        wall = perf_counter() - started
        calls = provider.posts[first:]
        steps = [{'tool': s['task_kind'], 'title': s['title'], 'status': s['status'],
                  'seconds': round(seconds_between(s.get('started_at'), s.get('ended_at')), 2)} for s in turn.get('tool_steps') or []]
        model = sum(c.get('seconds', 0) for c in calls)
        tools = sum(s['seconds'] for s in steps)
        turns.append({'label': label, 'persona': persona, 'question': prompt, 'status': turn['status'], 'wall_seconds': round(wall, 1),
                      'model_seconds': round(model, 1), 'lookup_seconds': round(tools, 1), 'other_seconds': round(wall - model - tools, 1),
                      'model_calls': calls, 'tool_steps': steps, 'reply_chars': len(turn.get('reply') or ''), 'reply': turn.get('reply')})
        print(f"{label}: {turn['status']} in {wall:.0f} s = model {model:.0f} s over {len(calls)} calls + lookups {tools:.0f} s + other {wall - model - tools:.0f} s", flush=True)
        for i, c in enumerate(calls, 1):
            print(f"   call {i}: {c.get('seconds')} s · prompt {c.get('prompt_tokens')} tok (cached {c.get('cached_tokens')}) · "
                  f"out {c.get('completion_tokens')} tok (reasoning {c.get('reasoning_tokens')}, {c.get('reasoning_chars')} chars) · "
                  f"answer {c.get('answer_chars')} chars · asks {c.get('tool_calls')} · {c['status']}", flush=True)

    output.mkdir(parents=True)
    secrets = [v for k, v in settings.items() if any(s in k.upper() for s in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY')) and len(v) > 8]
    text = json.dumps({'data': 'synthetic demo workspace in an isolated in-memory store', 'model': os.environ['LIFESCI_LLM_MODEL'],
                       'request_overrides': provider.extra, 'provider_requests': len(provider.posts), 'turns': turns}, indent=2, ensure_ascii=False)
    for value in secrets:
        text = text.replace(value, '<REDACTED>')
    (output / 'timings.json').write_text(text + '\n')
    print(json.dumps({'output': str(output), 'turns': len(turns), 'provider_requests': len(provider.posts)}))


if __name__ == '__main__':
    main()
