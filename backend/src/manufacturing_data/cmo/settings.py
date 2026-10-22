"""Load ingestion settings from .env.local without overwriting the shell."""
import os
from pathlib import Path


OPENAI_SETTINGS = {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_MODEL',
                   'OPENAI_REASONING_EFFORT', 'OPENAI_MAX_COMPLETION_TOKENS'}


def load_local_settings(path=None):
    path=Path(path) if path is not None else Path(__file__).resolve().parents[3]/'.env.local'
    if not path.is_file(): return
    from dotenv import dotenv_values
    for name,value in dotenv_values(path,interpolate=False).items():
        if name and (name.startswith(('CMO_','PHARMA_')) or name=='DOCLING_ARTIFACTS_PATH' or name in OPENAI_SETTINGS or name in {'CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_AUTH_TOKEN'}) and value:
            os.environ.setdefault(name,value)
