"""Protect real-request admission and honest incomplete reporting."""
import pytest


def test_request_reservations_prevent_concurrent_overspend():
    from benchmarks.agent_pilot.runner import CampaignBudget
    budget = CampaignBudget(1.0, 10, reserve_per_request=.6)
    first = budget.admit('a', 'agent')
    with pytest.raises(RuntimeError, match='budget'):
        budget.admit('b', 'agent')
    budget.settle(first, {'prompt_tokens': 1000, 'completion_tokens': 1000})
    second = budget.admit('b', 'judge')
    assert second != first
    assert budget.snapshot()['requests'] == 2


def test_unknown_usage_keeps_reservation_and_request_cap_is_hard():
    from benchmarks.agent_pilot.runner import CampaignBudget
    budget = CampaignBudget(10, 1, reserve_per_request=.5)
    first = budget.admit('a', 'agent')
    budget.settle(first, None)
    assert budget.snapshot()['accounted_usd'] == .5
    assert budget.snapshot()['unknown_usage_requests'] == 1
    with pytest.raises(RuntimeError, match='request'):
        budget.admit('b', 'agent')


def test_larger_token_request_reserves_its_estimated_upper_bound(tmp_path):
    from benchmarks.agent_pilot.runner import CampaignBudget
    budget = CampaignBudget(1, 3, receipt_dir=tmp_path)
    with pytest.raises(RuntimeError, match='budget'):
        budget.admit('a', 'judge', reserve_usd=1.1)
    index = budget.admit('a', 'agent', reserve_usd=.9)
    assert budget.snapshot()['accounted_usd'] == .9
    assert (tmp_path / 'request-00000.json').exists()
    budget.settle(index, None, status='error')
    import json
    assert json.loads((tmp_path / 'request-00000.json').read_text())['status'] == 'error'


def test_budget_rejects_invalid_or_negative_usage():
    from benchmarks.agent_pilot.runner import CampaignBudget
    budget = CampaignBudget(10, 2)
    req = budget.admit('a', 'agent')
    budget.settle(req, {'prompt_tokens': -1000, 'completion_tokens': 0})
    assert budget.snapshot()['unknown_usage_requests'] == 1


def test_judge_parser_rejects_multiple_or_non_object_answers():
    from benchmarks.agent_pilot.runner import parse_judge
    assert parse_judge('```json\n{"correct": true}\n```') == {'correct': True}
    assert parse_judge('[]') is None
    assert parse_judge('{"correct":true} {"correct":false}') is None


def test_episode_captures_real_reads_and_persists_model_results(tmp_path, monkeypatch):
    import json
    import time
    from benchmarks.agent_pilot import runner
    from benchmarks.agent_pilot.scenarios import build_suite
    from src.lifesci.gateway.providers import Completion
    case = build_suite('development', 1)[0]
    source_id = 'PILOT:development-discovery-1-review-register'
    verdict = {'supported': True, 'correct': True, 'complete': True,
        'uncertainty_appropriate': True, 'unsafe_claims': [], 'unsupported_claims': [],
        'evidence': [{'claim': 'D-01 exceeded acceptance', 'source_id': source_id,
            'quote': 'D-01 exceeded conductivity acceptance'}], 'reason': 'Source supports the finding.'}

    class ScriptedExternalProvider:
        def __init__(self, *args):
            self.posts = []
            self.purpose = 'agent'

        def complete(self, **kwargs):
            self.posts.append({'purpose': self.purpose})
            if self.purpose == 'judge':
                text = json.dumps(verdict)
            elif len(self.posts) == 1:
                text = json.dumps({'reply': 'Inspecting the register.', 'workflow': [{
                    'node_id': 'inspect', 'task_kind': 'workspace_read', 'title': 'Inspect register',
                    'payload': {'kind': 'evidence', 'record_id': source_id, 'revision': 1}, 'depends_on': []}]})
            else:
                text = json.dumps({'reply': 'D-01 exceeded conductivity acceptance; D-02 passed. The cause is unresolved.'})
            return Completion(text, 100, 100)

    monkeypatch.setattr(runner, 'RecordedProvider', ScriptedExternalProvider)
    monkeypatch.setenv('LIFESCI_LLM_PROVIDER', 'modal')
    monkeypatch.setenv('LIFESCI_LLM_MODEL', runner.MODEL)
    monkeypatch.delenv('LIFESCI_INTERPRETER_PROVIDER', raising=False)
    monkeypatch.delenv('LIFESCI_INTERPRETER_MODEL', raising=False)
    runner.configure_agent()
    path = tmp_path / 'episode'
    result = runner.run_episode(case, path, {}, runner.CampaignBudget(5, 10), time.monotonic() + 60)
    observation = json.loads((path / 'observation.json').read_text())
    assert observation['read_ids'] == [source_id]
    assert observation['source_revisions'][0]['content'].endswith('D-01 cause is unresolved.')
    assert result['status'] == 'PASS'
    assert result['trace']['mission_id']
    assert (path / 'workspace.sqlite').exists()


def test_judge_service_failure_is_not_an_agent_error(tmp_path, monkeypatch):
    import json
    import time
    from benchmarks.agent_pilot import runner
    from benchmarks.agent_pilot.scenarios import build_suite
    from src.lifesci.gateway.providers import Completion, ProviderError
    case = next(c for c in build_suite('development', 1) if c['family'] == 'memory')

    class JudgeUnavailable:
        def __init__(self, *args):
            self.posts = []
            self.purpose = 'agent'

        def complete(self, **kwargs):
            if self.purpose == 'judge':
                raise ProviderError('judge temporarily unavailable', retryable=False)
            self.posts.append({'purpose': self.purpose})
            return Completion(json.dumps({'reply': 'The ORBIT handoff batch is B-30, per your supplied context.'}), 100, 100)

    monkeypatch.setattr(runner, 'RecordedProvider', JudgeUnavailable)
    monkeypatch.setenv('LIFESCI_LLM_PROVIDER', 'modal')
    monkeypatch.setenv('LIFESCI_LLM_MODEL', runner.MODEL)
    monkeypatch.delenv('LIFESCI_INTERPRETER_PROVIDER', raising=False)
    monkeypatch.delenv('LIFESCI_INTERPRETER_MODEL', raising=False)
    runner.configure_agent()
    path = tmp_path / 'episode'
    result = runner.run_episode(case, path, {}, runner.CampaignBudget(5, 10), time.monotonic() + 60)
    observation = json.loads((path / 'observation.json').read_text())
    assert observation['errors'] == []
    assert result['checks']['host_errors']['passed'] is True
    assert result['status'] == 'NOT_GRADED'
    assert result['judge_error'] == {'type': 'ProviderError', 'attribution': 'evaluator_contract'}
