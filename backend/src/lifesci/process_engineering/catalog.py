"""Host-registered scientific adapters; agents choose IDs, never import paths."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Callable

from ..lyophilization import model
from . import transient


@dataclass(frozen=True)
class Adapter:
    id: str
    version: str
    title: str
    description: str
    required_inputs: tuple[str, ...]
    limitations: tuple[str, ...]
    run: Callable
    files: tuple[Path, ...]

    @property
    def digest(self):
        return hashlib.sha256(b"".join(p.read_bytes() for p in self.files)).hexdigest()

    def describe(self):
        return {"id": self.id, "version": self.version, "implementation_digest": self.digest,
                "title": self.title, "description": self.description, "required_inputs": list(self.required_inputs),
                "limitations": list(self.limitations), "process_family": "pharmaceutical_primary_drying",
                "qualification": "unqualified engineering demonstration", "source": model.PAPER,
                "supported_outputs": ["interface_temperature_c", "bottom_temperature_c", "remaining_ice_kg_per_vial", "sublimation_kg_h", "constraint_margins"],
                "units": "SI input keys; °C and hours explicitly named", "spatial_resolution": "representative vial / one-dimensional drying front"}

    def applicability(self, config):
        missing = []
        for key in self.required_inputs:
            current = config
            for part in key.split("."):
                current = current.get(part) if isinstance(current, dict) else None
            if current is None:
                missing.append(key)
        issues = []
        try:
            model.validate(config)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append(str(exc))
        if not missing and self.id == "lyo.transient_lumped":
            from ..lyophilization.model import _finite
            for key, bounds in [("vial_heat_capacity_j_k", (.1, 100.)), ("initial_temperature_c", (-65., -1.))]:
                try:
                    _finite(config["thermal"][key], key, *bounds)
                except ValueError as exc:
                    issues.append(str(exc))
        return {"applicable": not missing and not issues, "missing_inputs": missing, "issues": issues,
                "note": "Applicability checks input sufficiency, not scientific validation."}


class ModelCatalog:
    def __init__(self, process_family='pharmaceutical_primary_drying'):
        if process_family == 'aerobic_fermentation':
            from ..fermentation.model import adapters
            self.adapters = adapters()
            return
        if process_family != 'pharmaceutical_primary_drying':
            raise ValueError('unknown physical process family')
        core = Path(model.__file__)
        self.adapters = {
            "lyo.kv_rp": Adapter("lyo.kv_rp", model.MODEL_VERSION, "Quasi-steady Kv–Rp", "Rapid primary-drying screening with heat/mass balance and a moving ice front.", (),
                ("Neglects sensible-heat dynamics.", "Representative vial cannot establish hottest-vial protection.", "Prescribed pressure becomes invalid above vapor-handling capacity."), model.simulate, (core,)),
            "lyo.transient_lumped": Adapter("lyo.transient_lumped", transient.VERSION, "Transient thermal vial", "Adds finite vial/product thermal capacity to compare responses to scheduled changes.",
                ("thermal.vial_heat_capacity_j_k", "thermal.initial_temperature_c"),
                ("Additional uncharacterized thermal inputs may dominate results.", "Lumped node is not a resolved temperature or vapor-flow field.", "An extra state does not establish greater predictive accuracy."), transient.simulate, (core, Path(transient.__file__))),
        }

    def get(self, model_id):
        if model_id not in self.adapters:
            raise ValueError(f"unregistered physical model: {model_id}")
        return self.adapters[model_id]

    def snapshot(self, config=None):
        return [{**a.describe(), **({"applicability": a.applicability(config)} if config is not None else {})} for a in self.adapters.values()]
