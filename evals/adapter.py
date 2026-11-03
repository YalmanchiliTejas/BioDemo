"""Process-isolated adapter. Each operation opens only a synthetic SQLite store.

The parent never passes conversation history or reference answers to the worker.
The worker reconstructs context through normal application services.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic
from uuid import uuid4

from . import ROOT

class AdapterError(RuntimeError):
    pass

class SievanceMissionAdapter:
    def __init__(self, directory, *, timestamp, provider_env=None, max_requests=30,
                 timeout=420, providers=None, max_tool_calls=30):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.timestamp, self.timeout = timestamp, timeout
        self.provider_env = str(Path(provider_env).resolve()) if provider_env else None
        self.max_requests = max_requests
        self.max_tool_calls = max_tool_calls
        self.local_test_providers = providers  # pytest-only in-process worker seam
        self.tenant_id = 'eval-' + uuid4().hex[:12]
        self.sessions = {}
        self.mission_id = None
        self._last_session = None
        self.operations = 0

    @staticmethod
    def _worker_environment():
        from .providers import PROVIDER_KEYS
        keys=PROVIDER_KEYS | {'PATH','HOME','TMPDIR','LANG','LC_ALL','VIRTUAL_ENV',
            'SSL_CERT_FILE','REQUESTS_CA_BUNDLE','LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY','LANGFUSE_BASE_URL'}
        return {**{k:v for k,v in os.environ.items() if k in keys}, 'DEEPEVAL_TELEMETRY_OPT_OUT':'YES'}

    def _call(self, operation, **payload):
        self.operations += 1
        request = {'operation': operation, 'directory': str(self.directory),
                   'timestamp': self.timestamp, 'tenant_id': self.tenant_id,
                   'provider_env': self.provider_env, 'max_requests': self.max_requests, 'max_tool_calls': self.max_tool_calls,
                   **payload}
        if self.local_test_providers is not None:
            from .worker import execute
            result = execute(request, providers=self.local_test_providers)
        else:
            # Separate process is intentional: only the persistent store survives.
            completed = subprocess.run([sys.executable, '-m', 'evals.worker'],
                input=json.dumps(request), text=True, capture_output=True,
                cwd=ROOT, timeout=self.timeout,
                env=self._worker_environment())
            try:
                result = json.loads(completed.stdout)
            except ValueError:
                raise AdapterError(f'worker failed ({completed.returncode}); '
                                   f'{completed.stderr[-800:]}') from None
        if result.get('error'):
            raise AdapterError(result['error'])
        return result['result']

    def start_mission(self, case_id, tenant_id=None, *, objective=None, initial_documents=()):
        if tenant_id and tenant_id != self.tenant_id:
            raise ValueError('adapter uses one isolated tenant')
        result = self._call('start', case_id=case_id, objective=objective or case_id,
                            documents=list(initial_documents))
        self.mission_id = result['mission_id']
        return self.mission_id

    def open_session(self, mission_id, user_id='engineer'):
        result = self._call('open_session', mission_id=mission_id, user_id=user_id)
        self.sessions[result['id']] = True
        self._last_session = result['id']
        return result['id']

    def send_user_message(self, session_id, text):
        if not self.sessions.get(session_id):
            raise ValueError('session is closed or unknown')
        return self._call('message', session_id=session_id, text=text)

    def configure_followup(self, session_id, objective, *, every_minutes=None):
        return self._call('followup', session_id=session_id, objective=objective,
                          every_minutes=every_minutes)

    def ingest_document(self, mission_id, fixture_doc_id):
        if not isinstance(fixture_doc_id, dict):
            raise ValueError('provide the public document manifest, never a truth path')
        return self._call('ingest', mission_id=mission_id, document=fixture_doc_id)

    def emit_external_event(self, mission_id, event):
        return self._call('external_event', mission_id=mission_id, event=event)

    def advance_clock(self, iso_timestamp):
        from src.lifesci.ids import parse_iso
        if parse_iso(iso_timestamp) < parse_iso(self.timestamp):
            raise ValueError('clock cannot move backwards')
        self.timestamp = iso_timestamp

    def run_due_jobs(self):
        return self._call('tick')

    def close_session(self, session_id):
        if session_id not in self.sessions:
            raise ValueError('unknown session')
        self.sessions[session_id] = False
        # Closing a visit never cancels the separately authorized responsibility.
        return self._call('close_session', session_id=session_id)

    def restart_runtime(self):
        return self._call('restart')

    def drain_until_idle(self, max_steps=20):
        started = monotonic()
        for _ in range(max_steps):
            if monotonic() - started > self.timeout:
                raise TimeoutError('drain wall-time budget exhausted')
            result = self.run_due_jobs()
            if result['idle']:
                return result
            if result['blocked']:
                return result
        raise TimeoutError('drain step budget exhausted')

    def read_mission_state(self, mission_id):
        return self._call('snapshot', mission_id=mission_id)

    def _observations(self):
        path = self.directory / 'observations.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def read_notifications(self, mission_id):
        return self.read_mission_state(mission_id)['notifications']

    def read_action_log(self, mission_id):
        return [o for o in self._observations() if o['name'] == 'tool.call'
                and o.get('mission_id') == mission_id]

    def read_retrieval_log(self, mission_id):
        return [o for o in self._observations() if o['name'] in ('workspace.search', 'workspace.read')
                and o.get('mission_id') == mission_id]

    def get_trace_refs(self, mission_id):
        return [{k: o[k] for k in ('trace_id', 'observation_id', 'trace_url') if k in o}
                for o in self._observations() if o.get('mission_id') == mission_id and o.get('trace_id')]

    def cleanup(self, mission_id):
        # Evidence is retained for inspection; close connections without deleting runs.
        return self._call('cleanup', mission_id=mission_id)
