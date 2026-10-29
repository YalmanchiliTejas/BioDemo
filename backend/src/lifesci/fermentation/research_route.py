"""Reuse Prime's saved Modal model selection without copying its credentials.

Authentication stays in the SDK's existing AuthStorage/provider resolution.
No model qualification is created, and the normal gateway router is untouched.
"""
import json
import os
from pathlib import Path
from ..gateway.registry import ModelProfile


def hosted_research_profile():
    selected = os.getenv('BIODEMO_PRIME_RESEARCH_MODEL') or os.getenv('BIODEMO_PRIME_MODEL')
    if not selected:
        try:
            saved = json.loads((Path.home()/'.prime/agent/models.json').read_text())
            models = saved.get('providers', {}).get('modal', {}).get('models', [])
            if len(models) == 1:
                selected = 'modal/' + models[0]['id']
        except (OSError, ValueError, KeyError, TypeError):
            return None
    if not selected or not selected.startswith('modal/') or not selected[6:].strip():
        return None
    return ModelProfile('prime-modal-research', 'modal', selected[6:], 'M3', 0, 0, 0,
        price_source='Unknown hosted compute billing; zero ledger estimate is not measured free inference')
