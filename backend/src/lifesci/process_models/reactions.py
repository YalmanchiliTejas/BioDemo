"""Semi-batch extension of the existing chemical reactor's exact same rate laws."""
import numpy as np
from scipy.integrate import solve_ivp

from ..chemical_reactor.model import Chemistry, rates
from .common import Model, Input, positive, temperature, duration, series


CHEMISTRY_INPUTS = {
    "reference_temperature_k":temperature(), "product_rate_ref_s_inv":Input("1/s",0,.1),
    "impurity_rate_ref_s_inv":Input("1/s",0,.1), "product_activation_j_mol":Input("J/mol",0,150000),
    "impurity_activation_j_mol":Input("J/mol",0,150000),
    "product_enthalpy_j_mol":Input("J/mol",-300000,300000),
    "impurity_enthalpy_j_mol":Input("J/mol",-300000,300000),
    "density_kg_m3":positive("kg/m³",10000), "heat_capacity_j_kg_k":positive("J/(kg K)",10000)}


def semibatch(c):
    chemistry = Chemistry(**{key:float(c[key]) for key in CHEMISTRY_INPUTS})
    if c["initial_volume_m3"] >= c["maximum_volume_m3"]:
        raise ValueError("initial volume must be below maximum volume")
    if not 250 < c["initial_temperature_k"] < c["temperature_limit_k"] <= 450:
        raise ValueError("initial temperature must be inside the task/model envelope")
    if c["feed_until_s"] > c["duration_s"]:
        raise ValueError("feed cutoff must be inside the run")
    n0 = c["initial_a_mol_m3"]*c["initial_volume_m3"]
    state = np.array([n0,0.,0.,c["initial_temperature_k"]])
    volume = lambda t: c["initial_volume_m3"]+c["feed_flow_m3_s"]*min(t,c["feed_until_s"])
    boundaries = sorted(set([0., c["feed_until_s"], c["duration_s"]]))
    rows, stop_reasons = [], []
    calls = 0
    for left,right in zip(boundaries,boundaries[1:]):
        if right == left: continue
        q = c["feed_flow_m3_s"] if left < c["feed_until_s"] else 0.
        def rhs(t,y):
            nonlocal calls
            calls += 1
            if calls > 20000:
                raise ValueError("semi-batch numerical evaluation budget exceeded")
            kb,ki = rates(np.clip(y[3],250,450),chemistry)
            rb,ri = kb*y[0],ki*y[0]
            heat = -chemistry.product_enthalpy_j_mol*rb-chemistry.impurity_enthalpy_j_mol*ri
            heat -= c["heat_transfer_area_m2"]*c["heat_transfer_coefficient_w_m2_k"]*(y[3]-c["coolant_temperature_k"])
            heat += chemistry.density_kg_m3*q*chemistry.heat_capacity_j_kg_k*(c["feed_temperature_k"]-y[3])
            return [q*c["feed_a_mol_m3"]-rb-ri,rb,ri,
                    heat/(chemistry.density_kg_m3*volume(t)*chemistry.heat_capacity_j_kg_k)]
        def hot(t,y): return c["temperature_limit_k"]-y[3]
        def cold(t,y): return y[3]-250.
        def full(t,y): return c["maximum_volume_m3"]-volume(t)
        for event in (hot,cold,full):
            event.terminal=True
            event.direction=-1
        sol = solve_ivp(rhs,(left,right),state,method="BDF",rtol=1e-8,
                        atol=[max(n0,1.)*1e-10]*3+[1e-8],dense_output=True,
                        max_step=min(30.,(right-left)/100),events=[hot,cold,full])
        if not sol.success or not np.isfinite(sol.y).all():
            raise ValueError("semi-batch solver failed: "+sol.message)
        t = np.unique(np.r_[np.linspace(left,sol.t[-1],101),sol.t])
        y = sol.sol(t)
        current = series(t, a_mol=y[0],product_mol=y[1],impurity_mol=y[2],temperature_k=y[3],
                         volume_m3=np.array([volume(h) for h in t]))
        rows.extend(current if not rows else current[1:])
        state = sol.y[:,-1]
        stop_reasons = [name for name,ev in zip(("temperature_limit_reached","low_temperature_envelope","volume_limit_reached"),sol.t_events) if len(ev)]
        if stop_reasons: break
    denominator = n0+c["feed_flow_m3_s"]*c["feed_until_s"]*c["feed_a_mol_m3"]
    for row in rows:
        dose = n0+c["feed_flow_m3_s"]*min(row["time_s"],c["feed_until_s"])*c["feed_a_mol_m3"]
        row["product_yield_fraction"] = row["product_mol"]/dose
    if min(min(row[k] for k in ("a_mol","product_mol","impurity_mol")) for row in rows) < -max(n0,1)*1e-7:
        raise ValueError("negative species inventory")
    complete = not stop_reasons
    return {"trajectory":rows, "status":"completed" if complete else "stopped", "violations":stop_reasons,
            "product_yield_fraction":float(state[1]/denominator) if complete else None,
            "impurity_fraction":float(state[2]/denominator) if complete else None,
            "final_volume_m3":rows[-1]["volume_m3"],
            "maximum_a_equivalent_mole_error":max(abs(row["a_mol"]+row["product_mol"]+row["impurity_mol"]-
                (n0+c["feed_flow_m3_s"]*min(row["time_s"],c["feed_until_s"])*c["feed_a_mol_m3"])) for row in rows)}


MODELS = [Model("chemical.semi_batch", "chemical_synthesis", "Fed chemical reactor with competing impurity",
    {**CHEMISTRY_INPUTS, "initial_volume_m3":positive("m³",1000), "maximum_volume_m3":positive("m³",1000),
     "initial_a_mol_m3":positive("mol/m³",1e5), "initial_temperature_k":temperature(),
     "heat_transfer_area_m2":positive("m²",10000), "heat_transfer_coefficient_w_m2_k":Input("W/(m² K)",0,10000),
     "coolant_temperature_k":temperature(), "feed_flow_m3_s":Input("m³/s",0,1),
     "feed_a_mol_m3":Input("mol/m³",0,1e5), "feed_temperature_k":temperature(),
     "feed_until_s":Input("s",0,604800), "temperature_limit_k":temperature(), "duration_s":duration()},
    {"a_mol":"mol", "product_mol":"mol", "impurity_mol":"mol", "temperature_k":"K", "volume_m3":"m³", "product_yield_fraction":"fraction"},
    "dNA/dt=Q CAfeed-(kB+kI)NA; dNB/dt=kB NA; V=V0+Q min(t,tfeed); energy includes feed sensible heat",
    ("Reuses existing batch chemistry rate laws, constant density/Cp, no evaporation or nonideal mixing.",
     "Prescribed wetted area and coolant boundary; no jacket, chiller or area-vs-fill model.",
     "Two irreversible 1:1 pathways; not arbitrary reaction networks or validated isolated yield."),
    semibatch, "Conservation balances; shared kinetics from chemical_reactor/model.py")]
