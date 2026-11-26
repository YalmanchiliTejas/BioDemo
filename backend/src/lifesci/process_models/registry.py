"""Additive family registry; old model/service paths remain authoritative."""
from . import reactions, crystallization, isolation, powders, tablets, downstream, utilities


def models():
    definitions = [model for module in (reactions,crystallization,isolation,powders,tablets,downstream,utilities)
                   for model in module.MODELS]
    registry = {m.id:m for m in definitions}
    if len(registry) != len(definitions):
        raise ValueError("duplicate model identifiers")
    return registry


def get(model_id):
    # Compatibility facade: the product's ModelCatalog is the single lookup path.
    from ..process_engineering.catalog import ModelCatalog
    return ModelCatalog(None).get(model_id)


def existing_model_inventory():
    """Reuse references, not copies; unavailable external workers are not executed."""
    return [
        {"family":"chemical_batch_reaction","module":"src.lifesci.chemical_reactor.model","status":"existing_local_module"},
        {"family":"aerobic_fermentation","module":"src.lifesci.fermentation.model","status":"existing_characterization_models"},
        {"family":"pharmaceutical_primary_drying","module":"src.lifesci.lyophilization.model","status":"existing_local_module"},
        {"family":"bioprocess","module":"src.lifesci.bioprocess.simulators","status":"existing_pinned_external_worker_required"},
        {"family":"cho_batch","module":"src.lifesci.bioprocess.cho","status":"existing_local_module_with_documented_accuracy_limits"}]
