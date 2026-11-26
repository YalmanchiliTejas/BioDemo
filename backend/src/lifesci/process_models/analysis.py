"""Curve calibration and explicit sensitivity; no invented statistical confidence."""
from copy import deepcopy
import math

import numpy as np
from scipy.optimize import least_squares

from ..ids import content_hash
from .registry import get


def fit_parameter(model_id, config, *, parameter, bounds, observable, observations, training_until):
    """Fit one scalar from curve observations; all later observations are held out.

    Rows: {coordinate, value, source_ref}. Coordinate is the model's declared axis
    (seconds or Pa), never guessed from data. Scalar screens have no such axis.
    """
    model = get(model_id)
    base = model.validate(config)
    if not isinstance(observations,list) or any(not isinstance(row,dict) for row in observations):
        raise ValueError("observations must be a list of records")
    if model.axis == "none":
        raise ValueError("scalar screen requires a multi-experiment calibration, not this curve fitter")
    if parameter not in model.inputs or observable not in model.outputs or observable == model.axis:
        raise ValueError("parameter/observable not declared for this model")
    lo,hi = bounds
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (lo,hi,training_until)) or not lo < hi:
        raise ValueError("finite increasing parameter bounds and finite training cutoff required")
    for b in bounds:
        trial=deepcopy(base); trial[parameter]=float(b); model.validate(trial)
    if not lo <= base[parameter] <= hi:
        raise ValueError("starting parameter outside fit bounds")
    for row in observations:
        if set(row) != {"coordinate","value","source_ref"} or not isinstance(row["source_ref"],str) or not row["source_ref"].strip():
            raise ValueError("observations need coordinate, value and nonempty source_ref")
        if any(isinstance(row[k],bool) or not isinstance(row[k],(int,float)) or not math.isfinite(row[k]) for k in ("coordinate","value")):
            raise ValueError("observation coordinates/values must be finite numbers")
    if any(a["coordinate"] >= b["coordinate"] for a,b in zip(observations,observations[1:])):
        raise ValueError("observation coordinates must strictly increase")
    training = [r for r in observations if r["coordinate"] <= training_until]
    holdout = [r for r in observations if r["coordinate"] > training_until]
    if len(training)<3 or not holdout:
        raise ValueError("need at least three training points and one later holdout")
    calls=0
    def predict(value,rows):
        nonlocal calls
        trial=deepcopy(base); trial[parameter]=float(value); result=model.run(trial); calls+=1
        if result["status"] != "completed" or not result.get("trajectory"):
            raise ValueError("fit candidate cannot complete this task; no extrapolation")
        curve=result["trajectory"]
        axis=np.array([r[model.axis] for r in curve])
        if rows[0]["coordinate"] < axis[0] or rows[-1]["coordinate"] > axis[-1]:
            raise ValueError("observations outside model output axis")
        return np.interp([r["coordinate"] for r in rows],axis,[r[observable] for r in curve])
    # Scale the parameter to [0,1] to avoid mixing Pa^-1 and physical-unit steps.
    def residual(z): return predict(lo+(hi-lo)*z[0],training)-[r["value"] for r in training]
    fit=least_squares(residual,[(base[parameter]-lo)/(hi-lo)],bounds=([0.],[1.]),
                      max_nfev=50,ftol=1e-10,xtol=1e-10,gtol=1e-10)
    if not fit.success: raise ValueError("calibration failed: "+fit.message)
    estimate=float(lo+(hi-lo)*fit.x[0])
    holdout_error=predict(estimate,holdout)-[r["value"] for r in holdout]
    selected=deepcopy(base); selected[parameter]=estimate
    norm=float(np.linalg.norm(fit.jac))
    return {"model_id":model_id,"parameter":parameter,"estimate":estimate,"fitted_config":selected,
            "parameter_unit":model.inputs[parameter].unit,"observable":observable,"observable_unit":model.outputs[observable],
            "training_cutoff":training_until,"axis":model.axis,"training_rows":len(training),"holdout_rows":len(holdout),
            "training_rmse":float(np.sqrt(np.mean(fit.fun**2))),"holdout_rmse":float(np.sqrt(np.mean(holdout_error**2))),
            "at_bound":bool(np.any(fit.active_mask)),"scaled_jacobian_norm":norm,
            "identifiability":"weak_or_unexcited" if norm < 1e-8 else "nonzero_local_sensitivity_only",
            "solver_calls":calls,"training_hash":content_hash(training),"holdout_hash":content_hash(holdout),
            "scope":"Single-parameter fit conditional on every other supplied property; no cross-site validation or confidence interval"}


def compare(model_id, donor, receiver, *, metrics):
    model=get(model_id)
    a,b=model.run(donor),model.run(receiver)
    differences={}
    for key in metrics:
        x,y=a.get(key),b.get(key)
        if x is None or y is None or a["status"]!="completed" or b["status"]!="completed":
            differences[key]=None
        elif isinstance(x,(int,float)) and not isinstance(x,bool) and isinstance(y,(int,float)) and not isinstance(y,bool):
            differences[key]=y-x
        else:
            raise ValueError("comparison metric must be a top-level numeric output")
    return {"donor":a,"receiver":b,"receiver_minus_donor":differences,
            "input_changes":{k:{"donor":donor[k],"receiver":receiver[k]} for k in model.inputs if donor[k]!=receiver[k]},
            "classification":"conditional_scenario_comparison_not_transfer_validation",
            "warning":"Material identity/kinetic equivalence and metric acceptance need independent engineering review"}


def parameter_scenarios(model_id, config, *, parameter, values, metrics):
    model=get(model_id)
    if parameter not in model.inputs or not 1 <= len(values) <= 32:
        raise ValueError("known parameter and 1..32 explicit scenario values required")
    rows=[]
    for value in values:
        trial=deepcopy(config); trial[parameter]=value
        try:
            result=model.run(trial)
            rows.append({"value":value,"status":result["status"],"violations":result["violations"],
                         "metrics":{k:result.get(k) for k in metrics}})
        except ValueError as exc:
            rows.append({"value":value,"status":"failed","error":str(exc),"metrics":None})
    return {"model_id":model_id,"parameter":parameter,"rows":rows,
            "classification":"declared_sensitivity_scenarios_not_calibrated_uncertainty"}
