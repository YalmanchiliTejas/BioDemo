"""Opt-in actual Docker checks; no model requests or cloud credentials."""
import os
import uuid

import pytest

docker = pytest.importorskip("docker")
from src.cloud_backend.dispatcher import container_limits


@pytest.mark.skipif(os.getenv("RUN_CLOUD_DOCKER_TESTS") != "1", reason="Opt-in local Docker isolation probe")
def test_actual_agent_limits_prevent_host_writes_and_direct_egress():
    engine = docker.from_env()
    image = os.environ["CLOUD_TEST_IMAGE"]
    network = engine.networks.create("biodemo-isolation-test-" + uuid.uuid4().hex, internal=True)
    container = None
    proxy = None
    code = """
import os, socket
from pathlib import Path
assert os.getuid() == 10001
assert socket.gethostbyname('egress')
assert not Path('/var/run/docker.sock').exists()
assert not any(os.getenv(k) for k in ('DATABASE_URL','AWS_ACCESS_KEY_ID','SPACES_CREDENTIALS_FILE'))
try:
    Path('/app/should-not-write').write_text('forbidden')
except OSError:
    pass
else:
    raise AssertionError('Writable root filesystem')
Path('/tmp/allowed').write_text('ephemeral')
try:
    socket.create_connection(('1.1.1.1',443),timeout=2)
except OSError:
    pass
else:
    raise AssertionError('Direct external egress succeeded')
try:
    socket.getaddrinfo('example.com',443)
except socket.gaierror:
    pass
else:
    raise AssertionError('External DNS bypass succeeded')
assert '0000000000000000' in next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:'))
"""
    try:
        proxy = engine.containers.create(image, command=["python", "-c", "import time; time.sleep(30)"],
                                         network=network.name, networking_config={network.name:
                                             engine.api.create_endpoint_config(aliases=["egress"])}, **container_limits())
        proxy.start()
        container = engine.containers.create(image, command=["python", "-c", code], network=network.name,
                                             **container_limits())
        container.start()
        assert container.wait(timeout=30)["StatusCode"] == 0
    finally:
        if container:
            container.remove(force=True)
        if proxy:
            proxy.remove(force=True)
        network.remove()
