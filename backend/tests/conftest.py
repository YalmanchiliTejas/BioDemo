import pytest


@pytest.fixture(autouse=True)
def isolated_benchmark_state(tmp_path_factory, monkeypatch):
    """Case runs in tests must not touch the developer's input cache or runtime workspaces."""
    monkeypatch.setenv('BIODEMO_INPUT_CACHE', str(tmp_path_factory.mktemp('input-cache')))
    # The platform API mounts CMO delivery verification; keep its run store out of the developer cache.
    monkeypatch.setenv('CMO_INGESTION_ROOT', str(tmp_path_factory.mktemp('cmo-ingestion')))
    import benchmarks.common.persistent_trial as persistent_trial
    monkeypatch.setattr(persistent_trial, 'ROOT', tmp_path_factory.mktemp('benchmark-root'))
