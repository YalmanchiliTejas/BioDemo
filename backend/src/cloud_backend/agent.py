"""One attempt per container. No DB, broad object access or cloud credentials.

The Prime SDK and provider configuration must be baked into an approved agent
image. Raw evidence, model events and errors stay on ephemeral encrypted disk.
"""
import hashlib
import base64
import json
import os
import signal
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


def execute(manifest, work):
    from .crypto import seal, unseal
    from src.manufacturing_data import ManufacturingStore, ingest_package
    from src.prime_runtime.harness import PrimeManufacturingHarness
    from src.state import BlackboardStore
    from src.workflows import ManufacturingInvestigationWorkflow

    package = work / "input.zip"
    encrypted = bytearray()
    size = 0
    with urlopen(manifest["input_url"], timeout=30) as response:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 64 * 1024 * 1024 + 32:
                raise ValueError("Input exceeds limit")
            encrypted.extend(chunk)
    data = unseal(base64.b64decode(manifest["input_key"]), manifest["input_path"], bytes(encrypted))
    if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise ValueError("Input digest mismatch")
    package.write_bytes(data)
    store = ManufacturingStore(work / "store")
    ingested = ingest_package(package, store, access_scope=manifest["scope"])
    if ingested["errors"]:
        raise ValueError("Evidence preparation requires review")
    boards = BlackboardStore(work / "blackboards")
    workflow = ManufacturingInvestigationWorkflow(work / "workflow", store,
                                                 scope=manifest["scope"], blackboards=boards)
    harness = PrimeManufacturingHarness.from_env(store=store, blackboards=boards,
                                               workflow=workflow, scope=manifest["scope"])
    harness.timeout_seconds = max(1, int(manifest["deadline"] - time.time() - 15))
    harness.max_tool_calls = manifest["max_tool_calls"]
    result = harness.run(incident_id=manifest["id"], problem=manifest["objective"],
                         new_evidence_ids=[], as_of=manifest["as_of"])
    data = json.dumps({"run_id": manifest["id"], "input_sha256": manifest["sha256"],
                       "input_version_id": manifest["version_id"], "as_of": manifest["as_of"],
                       "review_status": "requires_human_review", "report": result}, default=str).encode()
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Result exceeds limit")
    data = seal(base64.b64decode(manifest["output_key"]), manifest["output_path"], data)
    with urlopen(Request(manifest["output_url"], data=data, method="PUT"), timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Result persistence failed")


def main():
    os.umask(0o077)
    # The task has no IAM role. No control-plane DSN or admin secrets may be injected.
    if any(os.getenv(k) for k in ("DATABASE_URL", "AWS_ACCESS_KEY_ID", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")):
        raise RuntimeError("Agent task must not receive infrastructure credentials")
    manifest = json.loads(os.environ.pop("JOB_MANIFEST"))
    seconds = int(manifest["deadline"] - time.time())
    if seconds <= 0:
        raise SystemExit(1)
    signal.alarm(seconds)
    try:
        with tempfile.TemporaryDirectory(prefix="agent-", dir="/tmp") as folder:
            execute(manifest, Path(folder))
    except Exception:
        # Do not send document contents or provider errors to shared task logs.
        print('{"event":"agent_failed"}', flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
