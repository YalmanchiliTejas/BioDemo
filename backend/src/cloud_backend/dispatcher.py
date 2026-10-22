"""Droplet dispatcher: durable admission and one hardened container per job.

Only this trusted service receives the Docker socket. Agent containers receive
object-specific keys and signed URLs, never database or Spaces credentials.
"""
import base64
import json
import os
import re
import time

import docker
from docker.types import LogConfig, Ulimit
from psycopg.types.json import Jsonb

from .api import input_key
from .crypto import master_key, object_key, spaces_client, unseal
from .store import Store


def container_limits():
    return {"user": "10001:10001", "read_only": True,
            "dns": ["127.0.0.1"],
            "tmpfs": {"/tmp": "rw,nosuid,nodev,size=1073741824,uid=10001,gid=10001,mode=0700"},
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "mem_limit": "2g", "nano_cpus": 2_000_000_000, "pids_limit": 128, "init": True,
            "log_config": LogConfig(type="none"), "restart_policy": {"Name": "no"},
            "ulimits": [Ulimit(name="core", soft=0, hard=0)]}


class Dispatcher:
    def __init__(self, store, engine, s3, config, encryption_key):
        self.store, self.engine, self.s3 = store, engine, s3
        self.config, self.master = config, encryption_key
        if not re.search(r"@sha256:[a-f0-9]{64}$", config["image"]):
            raise ValueError("Agent image must be pinned by digest")

    def prepare(self, job):
        request = job["request"]
        remaining = max(1, int(job["deadline"] - time.time()))
        source = input_key(job["tenant"], job["project"], request["sha256"])
        output = f'{job["tenant"]}/{job["project"]}/results/{job["id"]}/{job["fence"]}.json'
        return {**request, "id": job["id"], "scope": job["project"], "deadline": job["deadline"],
                "input_path": source, "output_path": output,
                "input_key": base64.b64encode(object_key(self.master, source)).decode(),
                "output_key": base64.b64encode(object_key(self.master, output)).decode(),
                "input_url": self.s3.generate_presigned_url("get_object", Params={
                    "Bucket": self.config["bucket"], "Key": source, "VersionId": request["version_id"]},
                    ExpiresIn=remaining + 60),
                "output_url": self.s3.generate_presigned_url("put_object", Params={
                    "Bucket": self.config["bucket"], "Key": output}, ExpiresIn=remaining + 60)}

    @staticmethod
    def name(job):
        return f'biodemo-job-{job["id"]}-{job["fence"]}'

    def container(self, job):
        try:
            return self.engine.containers.get(self.name(job))
        except docker.errors.NotFound:
            return None

    def launch(self, job):
        name = self.name(job)
        try:
            network = self.engine.networks.get(name)
        except docker.errors.NotFound:
            network = self.engine.networks.create(name, internal=True, check_duplicate=True,
                                                 labels={"biodemo.job": job["id"]})
        proxy = self.engine.containers.get(self.config["proxy"])
        proxy.reload()
        if name not in proxy.attrs["NetworkSettings"]["Networks"]:
            network.connect(proxy, aliases=["egress"])
        # No host directories, secret mounts, general cloud credentials or Docker socket.
        environment = {"JOB_MANIFEST": json.dumps(job["launch_manifest"]),
                       "HTTP_PROXY": "http://egress:3128", "HTTPS_PROXY": "http://egress:3128",
                       "http_proxy": "http://egress:3128", "https_proxy": "http://egress:3128",
                       "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
                       "BIODEMO_PRIME_MODEL": self.config["model"], "HOME": "/tmp",
                       "NODE_USE_ENV_PROXY": "1",
                       "PRIME_AGENT_BUNDLE_ROOT": "/opt/prime-agent",
                       self.config["model_secret_env"]: self.config["model_secret"]}
        return self.engine.containers.create(
            self.config["image"], name=name, command=["python", "-m", "src.cloud_backend.agent"],
            environment=environment, network=name, labels={"biodemo.job": job["id"]}, **container_limits())

    def cleanup(self, job):
        container = self.container(job)
        if container:
            container.remove(force=True)
        try:
            network = self.engine.networks.get(self.name(job))
            network.disconnect(self.config["proxy"], force=True)
            network.remove()
        except docker.errors.NotFound:
            pass
        with self.store.connect() as con:
            con.execute("UPDATE cloud_jobs SET task_arn=NULL,launch_manifest=NULL WHERE id=%s AND fence=%s",
                        (job["id"], job["fence"]))

    def validate_result(self, job):
        key = job["launch_manifest"]["output_path"]
        result = self.s3.get_object(Bucket=self.config["bucket"], Key=key)
        with result["Body"] as body:
            encrypted = body.read(16 * 1024 * 1024 + 33)
        if len(encrypted) > 16 * 1024 * 1024 + 32:
            raise ValueError("Result too large")
        value = json.loads(unseal(object_key(self.master, key), key, encrypted))
        if (value["run_id"] != job["id"] or value["input_sha256"] != job["request"]["sha256"] or
                value["review_status"] != "requires_human_review" or result.get("VersionId") in (None, "", "null")):
            raise ValueError("Invalid result")
        return key, result["VersionId"]

    def tick(self):
        with self.store.connect() as leader:
            if not leader.execute("SELECT pg_try_advisory_lock(7284091) AS acquired").fetchone()["acquired"]:
                return
            leader.commit()
            jobs = leader.execute("SELECT * FROM cloud_jobs WHERE state='running' OR launch_manifest IS NOT NULL").fetchall()
            leader.commit()
            for job in jobs:
                # A broken cloud operation for one job must not block cancellation/deadlines for others.
                try:
                    self.reconcile(leader, job)
                except Exception:
                    print(json.dumps({"event": "job_reconcile_failed", "job_id": job["id"]}), flush=True)
            with leader.transaction():
                self.store.claim(leader, self.config["max_active"])

    def reconcile(self, leader, job):
        if job["state"] != "running":
            self.cleanup(job)
            return
        if time.time() >= job["deadline"]:
            self.cleanup(job)
            self.store.finish(job["id"], job["fence"], "failed", error="deadline_exceeded")
            return
        if not job["launch_manifest"]:
            job["launch_manifest"] = self.prepare(job)
            with leader.transaction():
                changed = leader.execute("UPDATE cloud_jobs SET launch_manifest=%s WHERE id=%s AND state='running' RETURNING id",
                                         (Jsonb(job["launch_manifest"]), job["id"])).fetchone()
            if not changed:
                return
        container = self.container(job) or self.launch(job)
        container.reload()
        if container.status == "created":
            container.start()
            return
        if container.status in ("running", "restarting"):
            return
        success = container.attrs["State"].get("ExitCode") == 0
        key, version = None, None
        if success:
            try:
                key, version = self.validate_result(job)
            except Exception:
                success = False
        self.store.finish(job["id"], job["fence"], "succeeded" if success else "failed",
                          result_key=key, result_version=version, error=None if success else "agent_failed")
        self.cleanup(job)


def main():
    from pathlib import Path
    config = {"bucket": os.environ["ARTIFACT_BUCKET"], "image": os.environ["AGENT_IMAGE"],
              "model": os.environ["BIODEMO_PRIME_MODEL"], "proxy": os.environ["EGRESS_PROXY_CONTAINER"],
              "model_secret_env": os.environ["MODEL_SECRET_ENV"],
              "model_secret": Path(os.environ["MODEL_SECRET_FILE"]).read_text().strip(),
              "max_active": int(os.getenv("MAX_ACTIVE_AGENTS", "2"))}
    dispatcher = Dispatcher(Store(os.environ["DATABASE_URL"]), docker.from_env(), spaces_client(), config, master_key())
    while True:
        try:
            dispatcher.tick()
        except Exception:
            print('{"event":"dispatcher_reconcile_failed"}', flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
