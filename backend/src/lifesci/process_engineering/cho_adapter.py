"""Catalogue adapter for the existing CHO solver, without duplicating kinetics."""

from pathlib import Path
import hashlib
import numpy as np
from ..bioprocess import cho


class CHOAdapter:
    id = "cho.monod_batch"
    version = cho.VERSION

    @property
    def digest(self):
        return hashlib.sha256(Path(cho.__file__).read_bytes() + Path(__file__).read_bytes()).hexdigest()

    def describe(self):
        return {
            "id": self.id,
            "version": self.version,
            "implementation_digest": self.digest,
            "title": "Existing CHO Monod batch solver",
            "process_family": "cho_batch",
            "model_kind": "semimechanistic",
            "source": "Existing bioprocess/cho.py",
            "required_inputs": ["parameters", "initial_viable_cell_density", "initial_glucose", "duration_h"],
            "supported_outputs": {"viable_cell_density": "million cells/mL", "glucose": "g/L"},
            "axis": "time_h",
            "qualification": "unvalidated_transfer_forecast",
            "limitations": cho.LIMITATIONS,
            "note": "Verified delivery fitting/forecast remains available through existing cho_dataset_forecast; this adapter reuses integrate.",
        }

    def applicability(self, c):
        try:
            if set(c) - {
                "parameters",
                "initial_viable_cell_density",
                "initial_glucose",
                "duration_h",
                "evidence_classification",
                "source_refs",
            }:
                raise ValueError("Unsupported CHO input")
            p = np.array([c["parameters"][n] for n in cho.NAMES], dtype=float)
            if not np.isfinite(p).all() or np.any(p < cho.BOUNDS[0]) or np.any(p > cho.BOUNDS[1]):
                raise ValueError("CHO parameter outside declared bounds")
            vals = [c["initial_viable_cell_density"], c["initial_glucose"], c["duration_h"]]
            if not all(type(v) in (int, float) and np.isfinite(v) and v > 0 for v in vals) or c["duration_h"] > 120:
                raise ValueError("Positive initial states and duration <=120 h required")
            return {"applicable": True, "issues": []}
        except (ValueError, KeyError, TypeError) as exc:
            return {"applicable": False, "issues": [str(exc)]}

    def run(self, c):
        app = self.applicability(c)
        if not app["applicable"]:
            raise ValueError("; ".join(app["issues"]))
        t = np.linspace(0, c["duration_h"], 121)
        rows = cho.integrate(
            [c["parameters"][n] for n in cho.NAMES], [c["initial_viable_cell_density"], c["initial_glucose"]], 0.0, t
        )
        return {
            "status": "completed",
            "trajectory": [
                {"time_h": float(h), "viable_cell_density": float(x), "glucose": float(g)} for h, (x, g) in zip(t, rows)
            ],
            "violations": [],
            "limitations": cho.LIMITATIONS,
            "model_version": self.version,
        }
