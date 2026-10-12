from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DECOMPOSITION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"questions": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "question": {"type": "string"},
            "investigation_type": {"type": "string", "enum": [
                "historical", "batch_context", "batch_comparison", "process_environment",
                "equipment_maintenance", "quality_microbiology", "evidence_verification",
            ]},
            "batch_id": {"type": "string"}, "equipment_id": {"type": "string"},
            "search_term": {"type": "string"},
        },
        "required": ["question", "investigation_type", "batch_id", "equipment_id", "search_term"],
    }}},
    "required": ["questions"],
}

WORKER_PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"plans": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "question_id": {"type": "string"},
            "tool_requests": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "tool_name": {"type": "string", "enum": [
                        "search_factory_data", "get_batch_context", "compare_batches",
                        "analyze_trend", "get_evidence",
                    ]},
                    "arguments_json": {"type": "string"},
                },
                "required": ["tool_name", "arguments_json"],
            }},
        },
        "required": ["question_id", "tool_requests"],
    }}},
    "required": ["plans"],
}

WORKER_FINDING_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"findings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "question_id": {"type": "string"}, "finding": {"type": "string"},
            "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
            "contradicting_evidence_ids": {"type": "array", "items": {"type": "string"}},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["question_id", "finding", "supporting_evidence_ids", "contradicting_evidence_ids", "uncertainties"],
    }}},
    "required": ["findings"],
}

SYNTHESIS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "assessment": {"type": "string"},
        "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "hypotheses": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "hypothesis_id": {"type": "string"}, "statement": {"type": "string"},
                "confidence": {"type": "number"},
                "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "contradicting_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "unknowns": {"type": "array", "items": {"type": "string"}},
                "discriminators": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["hypothesis_id", "statement", "confidence", "supporting_evidence_ids", "contradicting_evidence_ids", "unknowns", "discriminators"],
        }},
        "evidence_requests": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "evidence_type": {"type": "string"}, "target": {"type": "string"},
                "reason": {"type": "string"}, "priority": {"type": "string"},
                "decision_dependency": {"type": "string"},
            },
            "required": ["evidence_type", "target", "reason", "priority", "decision_dependency"],
        }},
        "tasks": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "owner": {"type": "string", "enum": ["QA", "Microbiology", "MSAT", "Manufacturing", "Maintenance"]},
                "action": {"type": "string"}, "priority": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
            },
            "required": ["owner", "action", "priority", "evidence_ids", "reason"],
        }},
    },
    "required": ["assessment", "severity", "open_questions", "hypotheses", "evidence_requests", "tasks"],
}


class CodexRLMProvider:
    """Structured Luna reasoning through the user's authenticated Codex CLI."""

    provider_id = "codex.gpt-6-luna"

    def __init__(self, repository: Path, *, model: str = "gpt-6-luna", timeout_seconds: float = 300) -> None:
        self.repository = repository
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.system = (repository / "system.md").read_text(encoding="utf-8")
        self._lock = threading.Lock()
        self.calls = 0
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.output_tokens = 0
        self.reasoning_output_tokens = 0

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "model_calls": self.calls, "input_tokens": self.input_tokens,
                "cached_input_tokens": self.cached_input_tokens, "output_tokens": self.output_tokens,
                "reasoning_output_tokens": self.reasoning_output_tokens,
            }

    def _complete(self, stage: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        instructions = (
            "Do not use shell, filesystem, network, web, MCP, or any other tool. "
            "Analyze only the JSON payload below. Hidden benchmark data is unavailable and must not be inferred. "
            "Return only the JSON required by the output schema.\n\n"
            f"CANONICAL MANUFACTURING OS SPECIFICATION:\n{self.system}\n\n"
            f"STAGE: {stage}\nPAYLOAD:\n{json.dumps(payload, separators=(',', ':'), default=str)}"
        )
        with tempfile.TemporaryDirectory(prefix="biodemo-codex-rlm-") as temp:
            root = Path(temp)
            schema_path = root / "schema.json"
            output_path = root / "output.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            process = subprocess.run(
                [
                    "codex", "exec", "-m", self.model, "--ephemeral", "--sandbox", "read-only",
                    "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                    "-C", str(root), "--output-schema", str(schema_path),
                    "--output-last-message", str(output_path), "--json", "-",
                ],
                input=instructions, text=True, capture_output=True,
                timeout=self.timeout_seconds, check=False,
            )
            if process.returncode != 0:
                detail = process.stderr.strip() or process.stdout[-2000:]
                raise RuntimeError(f"Codex {stage} failed: {detail}")
            usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}
            forbidden_items: list[str] = []
            for line in process.stdout.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "turn.completed":
                    usage.update({key: int(value) for key, value in event.get("usage", {}).items() if key in usage})
                if event.get("type") == "item.completed":
                    item_type = str(event.get("item", {}).get("type", ""))
                    if item_type and item_type not in {"agent_message", "reasoning"}:
                        forbidden_items.append(item_type)
            if forbidden_items:
                raise RuntimeError(f"Codex {stage} violated no-tool boundary: {sorted(set(forbidden_items))}")
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Codex {stage} returned invalid structured output") from exc
        with self._lock:
            self.calls += 1
            self.input_tokens += usage["input_tokens"]
            self.cached_input_tokens += usage["cached_input_tokens"]
            self.output_tokens += usage["output_tokens"]
            self.reasoning_output_tokens += usage["reasoning_output_tokens"]
        return result

    def decompose(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("recursive_decomposition", payload, DECOMPOSITION_SCHEMA)

    def plan_workers(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("bounded_worker_tool_planning", payload, WORKER_PLAN_SCHEMA)

    def summarize_workers(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("compressed_worker_findings", payload, WORKER_FINDING_SCHEMA)

    def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("lead_rlm_synthesis", payload, SYNTHESIS_SCHEMA)


class OpenAIRLMProvider:
    """Structured RLM reasoning through the OpenAI Responses API."""

    provider_id = "openai.gpt-6-luna"

    def __init__(
        self,
        repository: Path,
        *,
        model: str = "gpt-6-luna",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 300,
    ) -> None:
        self.model = model
        self.provider_id = f"openai.{model}"
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OpenAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the OpenAI RLM provider")
        self.endpoint = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/") + "/responses"
        self.system = (repository / "system.md").read_text(encoding="utf-8")
        self._lock = threading.Lock()
        self.calls = 0
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.output_tokens = 0
        self.reasoning_output_tokens = 0

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "model_calls": self.calls, "input_tokens": self.input_tokens,
                "cached_input_tokens": self.cached_input_tokens, "output_tokens": self.output_tokens,
                "reasoning_output_tokens": self.reasoning_output_tokens,
            }

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        if not parts:
            raise RuntimeError(f"OpenAI response contained no output text (status={response.get('status', 'unknown')})")
        return "".join(parts)

    def _complete(self, stage: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        instructions = (
            "Do not use tools. Analyze only the JSON payload below. Hidden benchmark data is unavailable "
            "and must not be inferred. Return only the JSON required by the output schema.\n\n"
            f"CANONICAL MANUFACTURING OS SPECIFICATION:\n{self.system}\n\n"
            f"STAGE: {stage}\nPAYLOAD:\n{json.dumps(payload, separators=(',', ':'), default=str)}"
        )
        body = {
            "model": self.model,
            "input": instructions,
            "store": False,
            "text": {"format": {
                "type": "json_schema", "name": stage, "strict": True, "schema": schema,
            }},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        response: dict[str, Any] | None = None
        for attempt in range(12):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as raw:
                    response = json.loads(raw.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:2000]
                if exc.code not in {408, 409, 429, 500, 502, 503, 504} or attempt == 11:
                    raise RuntimeError(f"OpenAI {stage} failed with HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == 11:
                    raise RuntimeError(f"OpenAI {stage} request failed: {exc}") from exc
            time.sleep(min(30, 2 ** attempt))
        if response is None:
            raise RuntimeError(f"OpenAI {stage} request failed without a response")
        try:
            result = json.loads(self._output_text(response))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI {stage} returned invalid structured output") from exc
        usage = response.get("usage", {})
        input_details = usage.get("input_tokens_details", {}) or {}
        output_details = usage.get("output_tokens_details", {}) or {}
        with self._lock:
            self.calls += 1
            self.input_tokens += int(usage.get("input_tokens", 0))
            self.cached_input_tokens += int(input_details.get("cached_tokens", 0))
            self.output_tokens += int(usage.get("output_tokens", 0))
            self.reasoning_output_tokens += int(output_details.get("reasoning_tokens", 0))
        return result

    def decompose(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("recursive_decomposition", payload, DECOMPOSITION_SCHEMA)

    def plan_workers(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("bounded_worker_tool_planning", payload, WORKER_PLAN_SCHEMA)

    def summarize_workers(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("compressed_worker_findings", payload, WORKER_FINDING_SCHEMA)

    def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._complete("lead_rlm_synthesis", payload, SYNTHESIS_SCHEMA)
