# Local validation — 2026-10-22

Target: DigitalOcean SFO3 single-customer pilot. No cloud resources created.

- Cloud backend suite: **14 passed**, including real PostgreSQL transactions,
  restricted runtime role grants, token/authorization failures, idempotency,
  cancellation/fencing, dispatcher restart recovery, deadlines and encrypted
  backup round-trip verification.
- Actual Docker probe: non-root UID, no database/Spaces credentials or Docker
  socket, root filesystem writes denied, ephemeral `/tmp` writable, capabilities
  dropped, direct Internet access and external DNS denied, local proxy alias
  resolution available. Containers and networks removed after the probe.
- Control-plane Docker image built successfully, including encryption and
  backup dependencies.
- DigitalOcean Terraform initialized with the locked provider and validated.
- Compose configuration validated against example configuration. Python source
  compiled successfully.

Invocation for the opt-in integration checks:

```sh
RUN_CLOUD_DOCKER_TESTS=1 \
CLOUD_TEST_IMAGE=biodemo-cloud-control:security-test \
CLOUD_TEST_DATABASE_URL=postgresql://USER@HOST:PORT/DISPOSABLE_DATABASE \
.venv/bin/python -m pytest -q tests/cloud
```

Spaces and Docker queue reconciliation use fakes in the lifecycle tests; the
isolation probe uses real Docker. The encrypted backup test verifies streaming
encryption and recovery against synthetic dump bytes; it is not an operational
PostgreSQL restore drill. Real Spaces versioning, proxy/model connectivity,
Linux Prime agent image, identity-provider claims, encrypted-volume boot and
full database backup/restore remain deployment acceptance checks.

Account authentication was not configured on this machine. The API hostname,
actual identity provider and approved model endpoint still need configuration.
See [deployment and compliance work](cloud-backend.md) for the executable path
and outstanding operational controls.
