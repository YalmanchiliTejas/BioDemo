"""Small common contract; numerical bounds are not experimental qualification."""
from dataclasses import dataclass
import math
from pathlib import Path
import hashlib

import numpy as np
from scipy.integrate import solve_ivp

from ..ids import content_hash

VERSION = "pharma-reduced-model-library-1"


@dataclass(frozen=True)
class Input:
    unit: str
    minimum: float = 0.
    maximum: float = 1e15
    positive: bool = False


def positive(unit, maximum=1e15):
    return Input(unit, 0., maximum, True)


def fraction():
    return Input("fraction", 0., 1.)


def temperature():
    return Input("K", 250., 450.)


def duration():
    return positive("s", 604800.)


def grid(c):
    return np.linspace(0., c["duration_s"], 201)


def integrate(c, rhs, initial, *, events=None, atol=1e-9):
    """Bounded-size deterministic solve; include solver nodes and event endpoints."""
    calls = 0
    def bounded_rhs(t, y):
        nonlocal calls
        calls += 1
        if calls > 20000:
            raise ValueError("numerical evaluation budget exceeded; narrow the model/configuration")
        return rhs(t, y)
    sol = solve_ivp(bounded_rhs, (0., c["duration_s"]), initial, method="LSODA", rtol=1e-8,
                    atol=atol, dense_output=True, events=events, max_step=c["duration_s"]/100)
    if not sol.success or not np.isfinite(sol.y).all():
        raise ValueError("solver failed: " + sol.message)
    times = np.unique(np.r_[grid(c)[grid(c) <= sol.t[-1]], sol.t, sol.t[-1]])
    return times, sol.sol(times), sol


def series(times, **columns):
    return [{"time_s": float(t), **{key: float(values[i]) for key, values in columns.items()}}
            for i, t in enumerate(times)]


@dataclass(frozen=True)
class Model:
    id: str
    family: str
    title: str
    inputs: dict
    outputs: dict
    equation: str
    limitations: tuple
    calculate: object
    source: str
    kind: str = "reduced_mechanistic"
    axis: str = "time_s"

    @property
    def version(self):
        return VERSION

    @property
    def digest(self):
        # Include shared helpers and the reused batch kinetics, not just this adapter.
        paths = sorted(Path(__file__).parent.glob("*.py"))
        paths.append(Path(__file__).parent.parent / "chemical_reactor" / "model.py")
        return hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest()

    def describe(self):
        return {"id": self.id, "process_family": self.family, "title": self.title,
                "version": VERSION, "implementation_digest": self.digest, "model_kind": self.kind,
                "required_inputs": {k: {"unit": v.unit, "minimum": v.minimum,
                    "maximum": v.maximum, "strictly_positive": v.positive} for k, v in self.inputs.items()},
                "supported_outputs": self.outputs, "equation": self.equation, "source": self.source,
                "qualification": "experimental_no_customer_validation", "limitations": list(self.limitations),
                "evidence_required": ["evidence_classification", "source_refs"],
                "axis": self.axis}

    def validate(self, config):
        if not isinstance(config, dict):
            raise ValueError("configuration must be a mapping")
        expected = set(self.inputs) | {"evidence_classification", "source_refs"}
        missing, extra = expected-set(config), set(config)-expected
        if missing or extra:
            raise ValueError(f"missing fields: {sorted(missing)}; unsupported fields: {sorted(extra)}")
        for name, spec in self.inputs.items():
            value = config[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} requires a finite number in {spec.unit}")
            if not spec.minimum <= value <= spec.maximum or (spec.positive and value == 0):
                raise ValueError(f"{name} outside declared numerical bounds ({spec.unit})")
        if not isinstance(config["evidence_classification"], str) or not config["evidence_classification"].strip():
            raise ValueError("explicit evidence_classification required")
        refs = config["source_refs"]
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or not r.strip() for r in refs):
            raise ValueError("nonempty source_refs list required")
        return dict(config)

    def applicability(self, config):
        try:
            c = self.validate(config)
            # Input-level checks only; semantic relationships are checked on run.
            return {"applicable": True, "issues": [], "note": "Field sufficiency, not scientific validation; run checks related inputs"}
        except ValueError as exc:
            return {"applicable": False, "issues": [str(exc)]}

    def run(self, config):
        c = self.validate(config)
        output = self.calculate(c)
        output.setdefault("status", "completed")
        output.setdefault("violations", [])
        output.setdefault("warnings", [])
        output.update(model_id=self.id, model_version=VERSION, input_hash=content_hash(c),
                      implementation_digest=self.digest, evidence_classification=c["evidence_classification"],
                      source_refs=c["source_refs"], classification="conditional_model_calculation",
                      model_kind=self.kind, limitations=list(self.limitations))
        # Never serialize NaN/inf as a usable engineering result.
        def finite(value):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("nonfinite model output")
            if isinstance(value, dict):
                for item in value.values(): finite(item)
            if isinstance(value, (list, tuple)):
                for item in value: finite(item)
        finite(output)
        return output
