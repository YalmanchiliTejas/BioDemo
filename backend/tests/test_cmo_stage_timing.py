"""Stage timing regressions against SQLite and an opt-in isolated PostgreSQL DB."""
import math
import os
import uuid
from copy import deepcopy

import pytest

from src.lifesci.cmo_schema import CMO_DDL
from src.manufacturing_data.cmo.persistence import Repository, tenant_scope


@pytest.fixture(params=['sqlite', 'postgresql'])
def stage_repo(request, tmp_path, monkeypatch):
    if request.param == 'sqlite':
        yield Repository(str(tmp_path / 'stages.sqlite'))
        return
    dsn = os.getenv('CMO_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set CMO_TEST_DATABASE_URL to an isolated PostgreSQL database')
    psycopg = pytest.importorskip('psycopg')
    from psycopg import sql
    schema = 'cmo_stage_test_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        connection.execute(CMO_DDL)
    repository = Repository(dsn)
    # Reproduce a deployment/pooler whose text output defaults to 15 significant
    # digits. Each real connection starts at 0; repository transactions must
    # establish lossless float output themselves.
    monkeypatch.setattr(repository, '_connect', lambda: psycopg.connect(dsn,
        options=f'-c search_path={schema} -c extra_float_digits=0'))
    try:
        yield repository
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def _running_stage():
    return {'id': 'timing-regression', 'cmo': 'Synthetic stage timing test',
        'configuration': 'D', 'status': 'running', 'synthetic': True,
        'started_at': '2026-10-31T22:42:33+00:00',
        'stages': [{'stage': 'Ingest', 'state': 'running',
                    'elapsed_seconds': 0.04424858299989862}]}


def test_progress_checkpoint_preserves_exact_stage_timing(stage_repo):
    run = _running_stage()
    with tenant_scope('stage-timing-test'):
        stage_repo.save_run(run)
        run['stages'][0].update(state='complete', duration_seconds=0.16231459899997863)
        run['stages'].append({'stage': 'Classify', 'state': 'running',
                             'elapsed_seconds': 0.20656318199987725})
        stage_repo.save_run(run)
        # Repeated saves preserve completed timing values; no tolerance or
        # rewriting of the originally recorded stage start is permitted.
        stage_repo.save_run(run)
        with stage_repo.transaction() as tx:
            recorded = tx.fetchone('SELECT state, elapsed_seconds, duration_seconds '
                'FROM cmo_run_stages WHERE tenant_id=? AND run_id=? AND position=0',
                ('stage-timing-test', run['id']))
    assert recorded == ('complete', 0.04424858299989862, 0.16231459899997863)


def test_recorded_stage_start_still_rejects_a_one_bit_change(stage_repo):
    run = _running_stage()
    with tenant_scope('stage-timing-test'):
        stage_repo.save_run(run)
        changed = deepcopy(run)
        changed['stages'][0]['elapsed_seconds'] = math.nextafter(
            run['stages'][0]['elapsed_seconds'], math.inf)
        with pytest.raises(ValueError, match='elapsed_seconds cannot change'):
            stage_repo.save_run(changed)
