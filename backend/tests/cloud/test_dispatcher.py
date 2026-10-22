import io
import json
import time
from types import SimpleNamespace

import pytest
docker = pytest.importorskip("docker")
pytest.importorskip("psycopg")
pytest.importorskip("jwt")

from src.cloud_backend.crypto import object_key, seal
from src.cloud_backend.dispatcher import Dispatcher
from src.cloud_backend.store import Store
from test_security_backend import FakeSpaces, request, store


class Container:
    def __init__(self, name, **config):
        self.name, self.config, self.status = name, config, "created"
        self.attrs = {"State": {"ExitCode": 0}, "NetworkSettings": {"Networks": {}}}
        self.starts = 0

    def reload(self):
        pass

    def start(self):
        self.starts += 1
        self.status = "running"

    def remove(self, **kwargs):
        self.status = "removed"


class Engine:
    def __init__(self):
        self.created, self.items, self.nets = [], {}, {}
        proxy = Container("proxy")
        self.items["proxy"] = proxy

        def get(name):
            if name not in self.items or self.items[name].status == "removed":
                raise docker.errors.NotFound("missing")
            return self.items[name]

        def create(image, name, **config):
            self.items[name] = Container(name, image=image, **config)
            self.created.append(self.items[name])
            return self.items[name]

        def get_net(name):
            if name not in self.nets:
                raise docker.errors.NotFound("missing")
            return self.nets[name]

        def create_net(name, **config):
            def connect(container, **kwargs):
                container.attrs["NetworkSettings"]["Networks"][name] = {}
            net = SimpleNamespace(config=config, connect=connect, disconnect=lambda *a, **k: None,
                                  remove=lambda: self.nets.pop(name))
            self.nets[name] = net
            return net

        self.containers = SimpleNamespace(get=get, create=create)
        self.networks = SimpleNamespace(get=get_net, create=create_net)


def dispatcher(store):
    return Dispatcher(store, Engine(), FakeSpaces(), {"bucket": "private", "image": "agent@sha256:" + "a"*64,
        "proxy": "proxy", "model": "approved/model", "model_secret_env": "PROVIDER_KEY",
        "model_secret": "provider-only", "max_active": 1}, b"k" * 32)


def test_restart_reuses_container_and_cancellation_reclaims_it(store):
    dispatch = dispatcher(store)
    first = store.submit("tenant", "project", "alice", "first-job", request())
    second = store.submit("tenant", "project", "alice", "second-job", request())
    dispatch.tick()  # admission
    dispatch.tick()  # create and start
    assert len(dispatch.engine.created) == 1
    created = dispatch.engine.created[0]
    assert created.status == "running"
    config = created.config
    assert config["read_only"] and config["network"] in dispatch.engine.nets
    assert dispatch.engine.nets[config["network"]].config["internal"]
    assert "volumes" not in config and "DATABASE_URL" not in config["environment"]
    assert config["cap_drop"] == ["ALL"] and config["pids_limit"] == 128
    assert "SPACES_CREDENTIALS_FILE" not in config["environment"]
    # New dispatcher process recovers the durable manifest and existing task.
    restarted = Dispatcher(Store(store.dsn), dispatch.engine, dispatch.s3, dispatch.config, dispatch.master)
    restarted.tick()
    assert len(dispatch.engine.created) == 1 and created.starts == 1
    assert store.get("tenant", "project", second["id"], "alice")["state"] == "queued"
    store.cancel("tenant", "project", first["id"], "alice")
    restarted.tick()
    assert created.status == "removed" and not dispatch.engine.nets
    assert store.get("tenant", "project", second["id"], "alice")["state"] == "running"


def test_deadline_stops_task_and_late_completion_is_rejected(store):
    dispatch = dispatcher(store)
    job = store.submit("tenant", "project", "alice", "timeout-job", request())
    dispatch.tick()
    dispatch.tick()
    active = store.get("tenant", "project", job["id"], "alice")
    with store.connect() as con:
        con.execute("UPDATE cloud_jobs SET deadline=%s WHERE id=%s", (time.time() - 1, job["id"]))
    dispatch.tick()
    assert dispatch.engine.created[0].status == "removed"
    assert store.get("tenant", "project", job["id"], "alice")["error_code"] == "deadline_exceeded"
    assert not store.finish(job["id"], active["fence"], "succeeded")


def test_encrypted_result_is_validated_before_completion(store):
    dispatch = dispatcher(store)
    job = store.submit("tenant", "project", "alice", "result-job", request())
    dispatch.tick()
    dispatch.tick()
    active = store.get("tenant", "project", job["id"], "alice")
    key = active["launch_manifest"]["output_path"]
    data = json.dumps({"run_id": job["id"], "input_sha256": request()["sha256"],
                       "review_status": "requires_human_review", "report": {}}).encode()
    dispatch.s3.objects[key] = seal(object_key(dispatch.master, key), key, data)
    dispatch.engine.created[0].status = "exited"
    dispatch.tick()
    finished = store.get("tenant", "project", job["id"], "alice")
    assert finished["state"] == "succeeded" and finished["result_version"] == "version-1"
    assert dispatch.engine.created[0].status == "removed"


def test_crash_between_container_create_and_start_resumes_existing_task(store):
    dispatch = dispatcher(store)
    job = store.submit("tenant", "project", "alice", "launch-crash", request())
    dispatch.tick()
    created = dispatch.engine.created
    original_start = Container.start

    def crash(_):
        raise RuntimeError("simulated dispatcher restart before start")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Container, "start", crash)
        dispatch.tick()
    assert len(created) == 1 and created[0].status == "created"
    dispatch.tick()
    assert len(created) == 1 and created[0].starts == 1
