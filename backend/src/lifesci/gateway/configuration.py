"""Explicit engineering LLM bindings; configuration never grants qualification."""
import math
from collections.abc import Mapping

from ..ids import content_hash
from .registry import ModelProfile

ENGINEERING_TASKS = {'investigation_planning': 'planner', 'comparison_explanation': 'interpreter'}


def configure_engineering_llms(registry, environ: Mapping[str, str]) -> dict[str, str]:
    """Use one model by default, with an optional interpreter override.

    API secrets remain with the provider adapters. Unspecified prices are
    budgeting assumptions, exposed in route metadata, not actual billed cost.
    """
    provider = environ.get('LIFESCI_LLM_PROVIDER', '').strip()
    model = environ.get('LIFESCI_LLM_MODEL', '').strip()
    override_provider = environ.get('LIFESCI_INTERPRETER_PROVIDER', '').strip()
    override_model = environ.get('LIFESCI_INTERPRETER_MODEL', '').strip()
    if not any((provider, model, override_provider, override_model)):
        return {}
    if not provider or not model:
        raise ValueError('set both LIFESCI_LLM_PROVIDER and LIFESCI_LLM_MODEL')
    if override_provider and not override_model:
        raise ValueError('LIFESCI_INTERPRETER_PROVIDER also requires LIFESCI_INTERPRETER_MODEL')
    bindings = {}
    for task, role in ENGINEERING_TASKS.items():
        selected_provider = (override_provider or provider) if role == 'interpreter' else provider
        selected_model = (override_model or model) if role == 'interpreter' else model
        if selected_provider not in ('anthropic', 'openai'):
            raise ValueError('LIFESCI LLM provider must be anthropic or openai')
        if len(selected_model) > 200 or any(c in selected_model for c in ('\n', '\r')):
            raise ValueError('LLM model must be an exact API model/deployment identifier, at most 200 characters')
        prefix = 'LIFESCI_INTERPRETER' if role == 'interpreter' and override_model else 'LIFESCI_LLM'
        rates = {}
        supplied = []
        for name, default in (('INPUT', 10.), ('OUTPUT', 50.), ('CACHED_INPUT', 10.)):
            key = f'{prefix}_{name}_USD_PER_MTOK'
            supplied.append(key in environ)
            try:
                value = float(environ.get(key, str(default)))
                if not math.isfinite(value) or value < 0:
                    raise ValueError()
            except ValueError:
                raise ValueError(f'{key} must be finite and nonnegative') from None
            rates[name] = value
        price_source = 'operator_configured_estimate' if all(supplied) else 'development_budget_assumptions_not_provider_prices'
        profile_id = f'engineering-{role}'
        # Tier is the existing task floor, never evidence of model quality.
        version = content_hash({'provider': selected_provider, 'model': selected_model, 'rates': rates,
            'endpoint': environ.get(f'{selected_provider.upper()}_BASE_URL', 'provider_default')})[:16]
        registry.add_profile(ModelProfile(profile_id, selected_provider, selected_model, registry.policies[task].min_tier,
            rates['INPUT'], rates['OUTPUT'], rates['CACHED_INPUT'], price_source=price_source, version=version))
        bindings[task] = profile_id
    return bindings
