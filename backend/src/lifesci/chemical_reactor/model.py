"""Constant-volume, perfectly mixed batch reactor: A -> B and A -> I.

Moles: dNA/dt=-(kB+kI)NA, dNB/dt=kB NA, dNI/dt=kI NA.
Energy: rho V Cp dT/dt=(-dHB)kB NA+(-dHI)kI NA-UA(T-Tc).
Rates use k(T)=k_ref exp[-Ea/R (1/T-1/Tref)]. SI throughout.
The equal 1:1 stoichiometry conserves A-equivalent moles, not arbitrary
chemical mass: real chemistry needs molecular weights and stoichiometry.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ids import content_hash

VERSION = "parallel-batch-reaction-1"
R = 8.314462618  # J/(mol K)
LIMITS = [
    "Experimental decision-support model, not an experimentally validated process or safety study.",
    "Perfectly mixed constant-volume liquid, constant density/Cp and effective U; no feed or evaporation.",
    "Prescribed constant coolant temperature: no jacket, chiller, mixing or utility dynamics.",
    "Two irreversible first-order 1:1 pathways only; molar yield is not isolated mass yield or potency.",
    "Configured bounds are numerical/task bounds, not a demonstrated physical validity envelope.",
    "Thermal assessment is limited to this model and numerical resolution; no plant safety guarantee.",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Chemistry(Strict):
    reference_temperature_k: float = Field(gt=250, lt=450)
    product_rate_ref_s_inv: float = Field(ge=0, le=.1)
    impurity_rate_ref_s_inv: float = Field(ge=0, le=.1)
    product_activation_j_mol: float = Field(ge=0, le=150000)
    impurity_activation_j_mol: float = Field(ge=0, le=150000)
    product_enthalpy_j_mol: float = Field(ge=-300000, le=300000)
    impurity_enthalpy_j_mol: float = Field(ge=-300000, le=300000)
    density_kg_m3: float = Field(gt=0)
    heat_capacity_j_kg_k: float = Field(gt=0)


class Equipment(Strict):
    working_volume_m3: float = Field(gt=0, le=1000)
    heat_transfer_area_m2: float = Field(gt=0)
    heat_transfer_coefficient_w_m2_k: float = Field(ge=0, le=10000)
    coolant_temperature_k: float = Field(ge=250, le=450)


class Recipe(Strict):
    initial_a_mol_m3: float = Field(gt=0)
    initial_temperature_k: float = Field(gt=250, lt=450)
    duration_s: float = Field(gt=0, le=604800)
    temperature_limit_k: float = Field(gt=250, le=450)
    maximum_impurity_fraction: float = Field(ge=0, le=1)
    sample_interval_s: float = Field(gt=0)

    @model_validator(mode="after")
    def check(self):
        if self.initial_temperature_k >= self.temperature_limit_k:
            raise ValueError("initial temperature must be below the task temperature limit")
        if math.ceil(self.duration_s / self.sample_interval_s) > 10000:
            raise ValueError("at most 10,000 output intervals")
        return self


class Config(Strict):
    chemistry: Chemistry
    equipment: Equipment
    recipe: Recipe
    evidence_classification: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


def validate(config):
    return config if isinstance(config, Config) else Config.model_validate(config)


def rates(temperature_k, chemistry):
    return tuple(k * np.exp(-ea / R * (1 / temperature_k - 1 / chemistry.reference_temperature_k))
                 for k, ea in ((chemistry.product_rate_ref_s_inv, chemistry.product_activation_j_mol),
                               (chemistry.impurity_rate_ref_s_inv, chemistry.impurity_activation_j_mol)))


def simulate(config, *, kinetic_model=None):
    c = validate(config)
    ch, eq, recipe = c.chemistry, c.equipment, c.recipe
    n0 = recipe.initial_a_mol_m3 * eq.working_volume_m3
    capacity = ch.density_kg_m3 * eq.working_volume_m3 * ch.heat_capacity_j_kg_k
    ua = eq.heat_transfer_area_m2 * eq.heat_transfer_coefficient_w_m2_k

    evaluations = 0
    def rhs(t, y):
        nonlocal evaluations
        evaluations += 1
        if evaluations > 20000:
            raise ValueError("chemical solver evaluation budget exhausted")
        # Numerical trial steps may leave the envelope before event localization.
        # Clip rate evaluation only for those trial steps; stop at the envelope event.
        kb, ki = rates(np.clip(y[3], 250., 450.), ch)
        if kinetic_model is not None:
            factors = kinetic_model(y, c)
            if len(factors) != 2 or any(not math.isfinite(v) or not .25 <= v <= 4. for v in factors):
                raise ValueError("kinetic factors must remain in [.25, 4]")
            kb, ki = kb*factors[0], ki*factors[1]
        rb, ri = kb * y[0], ki * y[0]
        heat = -ch.product_enthalpy_j_mol * rb - ch.impurity_enthalpy_j_mol * ri
        return [-rb - ri, rb, ri, (heat - ua * (y[3] - eq.coolant_temperature_k)) / capacity]

    def upper(t, y):
        return min(recipe.temperature_limit_k, 450.) - y[3]

    def lower(t, y):
        return y[3] - 250.

    upper.terminal = lower.terminal = True
    upper.direction = lower.direction = -1
    sol = solve_ivp(rhs, (0, recipe.duration_s), [n0, 0., 0., recipe.initial_temperature_k],
                    method="BDF", rtol=1e-8, atol=[n0*1e-10]*3 + [1e-8],
                    dense_output=True, events=[upper, lower],
                    max_step=min(30., recipe.sample_interval_s))
    upper_hit, lower_hit = bool(len(sol.t_events[0])), bool(len(sol.t_events[1]))
    stop = float(sol.t[-1])
    times = np.unique(np.r_[np.arange(0, stop, recipe.sample_interval_s), sol.t, stop])
    states = sol.sol(times)
    bad_state = not np.isfinite(states).all() or states[:3].min() < -n0*1e-7
    complete = bool(sol.success and not upper_hit and not lower_hit and not bad_state
                    and abs(stop - recipe.duration_s) < 1e-6)
    rows = [{"time_s": float(t), "a_mol": float(a), "product_mol": float(b),
             "impurity_mol": float(i), "temperature_k": float(temp),
             "product_yield_fraction": float(b/n0), "impurity_fraction": float(i/n0)}
            for t, (a, b, i, temp) in zip(times, states.T)]
    b, i = float(states[1, -1]/n0), float(states[2, -1]/n0)
    violations = []
    if upper_hit:
        violations.append("temperature_limit_reached")
    if lower_hit:
        violations.append("temperature_below_model_envelope")
    if i > recipe.maximum_impurity_fraction:
        violations.append("impurity_limit_exceeded")
    if bad_state:
        violations.append("invalid_numerical_state")
    return {"model_version": VERSION, "input_hash": content_hash(c.model_dump()),
            "classification": "conditional_model_prediction", "evidence_classification": c.evidence_classification,
            "source_refs": c.source_refs, "status": "completed" if complete else "stopped_or_failed",
            "solver": {"method": "BDF", "scipy_version": scipy.__version__, "success": bool(sol.success),
                       "message": sol.message, "maximum_step_s": min(30., recipe.sample_interval_s)},
            "completed_duration_s": stop, "trajectory": rows,
            "product_yield_fraction": b if complete else None,
            "impurity_fraction": i if complete else None,
            "conversion_fraction": float(1-states[0, -1]/n0) if complete else None,
            "maximum_temperature_k_at_returned_points": float(states[3].max()),
            "maximum_a_equivalent_mole_error": float(np.max(np.abs(states[:3].sum(axis=0)-n0))),
            "violations": violations, "within_declared_constraints": complete and not violations,
            "limitations": LIMITS}


@dataclass(frozen=True)
class ReactorAdapter:
    id: str = "chemical.parallel_batch"
    version: str = VERSION

    @property
    def digest(self):
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def describe(self):
        return {"id": self.id, "version": self.version, "implementation_digest": self.digest,
                "process_family": "chemical_batch_reaction", "title": "Jacketed batch reaction with competing impurity",
                "required_inputs": list(Config.model_fields), "units": "Explicit SI keys; time in seconds, temperature K",
                "supported_outputs": ["temperature_k", "conversion_fraction", "product_yield_fraction", "impurity_fraction"],
                "qualification": "experimental_not_customer_validated", "limitations": LIMITS}

    def applicability(self, config):
        try:
            validate(config)
            return {"applicable": True, "issues": [], "note": "Input sufficiency only, not physical validation"}
        except ValueError as exc:
            return {"applicable": False, "issues": [str(exc)]}

    def run(self, config):
        return simulate(config)
