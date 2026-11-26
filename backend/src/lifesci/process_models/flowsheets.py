"""Explicit mass handoffs, without inventing unavailable process/property links."""
from copy import deepcopy

from .registry import get


def purification_train(*, crystal, filtration, wash, dryer, retained_liquid_m3, liquid_density_kg_m3):
    """Crystallise -> filter -> wash -> dry with specified retained mother liquor.

    This assumes common API/solvent identity across supplied unit configurations.
    Mother-liquor dissolved API is accounted separately from removable pore impurity.
    Washing's wash-solubility loss screen is additional API loss, not recycled API.
    """
    if isinstance(retained_liquid_m3,bool) or isinstance(liquid_density_kg_m3,bool) or not 0 < retained_liquid_m3 < crystal["liquid_volume_m3"] or not 0 < liquid_density_kg_m3 <= 20000:
        raise ValueError("positive retained liquid smaller than initial liquid and positive liquid density required")
    first=get("crystal.cooling_moments").run(crystal)
    solids=first["final_crystal_mass_kg"]
    if solids <= 0: raise ValueError("no crystals available for isolation")
    volume=crystal["liquid_volume_m3"]
    if solids/crystal["crystal_density_kg_m3"]/volume > .2:
        raise ValueError("this simple handoff assumes dilute slurry solids volume <=20% of liquid volume")
    f=deepcopy(filtration)
    f.update(target_filtrate_m3=volume-retained_liquid_m3,
             solids_per_filtrate_kg_m3=solids/(volume-retained_liquid_m3))
    second=get("isolation.cake_filter").run(f)
    stages=[{"model_id":first["model_id"],"input_hash":first["input_hash"],"status":first["status"]},
            {"model_id":second["model_id"],"input_hash":second["input_hash"],"status":second["status"]}]
    if second["status"]!="completed":
        return {"status":"blocked","stages":stages,"crystal_derived_isolated_api_kg":None,
                "reason":"filter did not complete; downstream steps were not run"}
    w=deepcopy(wash)
    w.update(initial_crystal_kg=solids,retained_liquid_m3=retained_liquid_m3)
    third=get("isolation.cake_wash").run(w)
    stages.append({"model_id":third["model_id"],"input_hash":third["input_hash"],"status":third["status"]})
    if third["retained_product_kg"]<=0:
        return {"status":"blocked","stages":stages,"crystal_derived_isolated_api_kg":None,"reason":"wash dissolved all solid API"}
    d=deepcopy(dryer)
    d.update(dry_solids_kg=third["retained_product_kg"],
             initial_solvent_kg_kg_dry=retained_liquid_m3*liquid_density_kg_m3/third["retained_product_kg"])
    fourth=get("isolation.cake_dryer").run(d)
    stages.append({"model_id":fourth["model_id"],"input_hash":fourth["input_hash"],"status":fourth["status"],
                   "violations":fourth["violations"]})
    accepted=fourth["status"]=="completed" and fourth["solvent_target_met"]
    initial=first["final_crystal_mass_kg"]+first["final_dissolved_mass_kg"]
    # Cake pore API stays in liquid phase; no additional crystallisation on drying
    # is predicted. Report crystal-derived isolated API only to avoid double counting.
    final=third["retained_product_kg"]
    return {"status":"completed" if accepted else "not_demonstrated","stages":stages,
            "initial_api_including_seed_kg":initial,
            "crystal_derived_isolated_api_kg":final if accepted else None,
            "mother_liquor_dissolved_api_kg":first["final_dissolved_mass_kg"],
            "wash_dissolved_api_kg":third["product_loss_kg"],
            "api_inventory_accounting_error_kg":abs(initial-final-first["final_dissolved_mass_kg"]-third["product_loss_kg"]),
            "final_residual_solvent_kg_kg_dry":fourth["final_solvent_kg_kg_dry"],
            "classification":"synthetic_assumption_flowsheet_not_validated_transfer",
            "limitations":["Common API/solvent assumed; density and liquid holdup must be supplied.",
                "No dissolved API reprecipitation, impurity partition or mother-liquor recycle model.",
                "Dry solids and yield track crystal-derived API only, not assay-corrected final cake mass.",
                "No heat/utility sharing or interactions beyond the explicitly mapped mass handoffs."]}
