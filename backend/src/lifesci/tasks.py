"""Work that continues after a response has been sent.

On a long-lived server a task runs in a background thread. On AWS Lambda the
instance is frozen as soon as the response returns, so a task is sent to the
same function as an asynchronous invocation instead and runs there with its own
time limit. Both paths call the same handler with the same JSON payload, so
every task carries everything it needs (tenant, actor, record ids) rather than
objects from the request.

Handlers must be safe to receive twice: Lambda delivers asynchronous events at
least once.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)
TASK_KEY = "biodemo_task"


def on_lambda() -> bool:
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


class TaskRunner:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def register(self, kind: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._handlers[kind] = handler

    def submit(self, kind: str, payload: dict[str, Any]) -> None:
        if kind not in self._handlers:
            raise KeyError(f"no handler registered for task {kind!r}")
        body = json.dumps({TASK_KEY: {"kind": kind, "payload": payload}})  # also proves the payload is serializable
        if on_lambda():
            import boto3

            response = boto3.client("lambda").invoke(FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
                                                     InvocationType="Event", Payload=body.encode())
            if response.get("StatusCode") != 202:
                raise RuntimeError(f"task {kind} was not accepted for asynchronous execution")
            return
        threading.Thread(target=self._run_logged, args=(kind, json.loads(body)[TASK_KEY]["payload"]),
                         daemon=True, name=f"task-{kind}").start()

    def _run_logged(self, kind: str, payload: dict[str, Any]) -> None:
        try:
            self._handlers[kind](payload)
        except Exception:
            log.exception("Background task %s failed; its record shows the failure or can be retried", kind)

    @staticmethod
    def is_task(event: Any) -> bool:
        return isinstance(event, dict) and isinstance(event.get(TASK_KEY), dict)

    def run(self, event: dict[str, Any]) -> Any:
        """Execute a task event delivered to this process (Lambda asynchronous invocation or schedule)."""
        task = event[TASK_KEY]
        kind = task.get("kind")
        if kind not in self._handlers:
            raise KeyError(f"no handler registered for task {kind!r}")
        return self._handlers[kind](task.get("payload") or {})
