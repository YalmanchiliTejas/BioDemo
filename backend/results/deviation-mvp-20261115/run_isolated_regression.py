import os,sys
from pathlib import Path
root=Path('/Users/tejas/Desktop/BioDemo')
for key in list(os.environ):
    if key not in {'PATH','HOME','TMPDIR','LANG','LC_ALL','LC_CTYPE','SYSTEMROOT'}:
        os.environ[key]=''
os.environ.update(PYTHONPATH=str(root/'backend'),LIFESCI_ENV_FILE='/dev/null',LIFESCI_DATABASE_URL='',DATABASE_URL='',CMO_DATABASE_URL='',CMO_TEST_DATABASE_URL='',CMO_HOSTED_INFERENCE_APPROVED='0')
sys.path[:0]=[str(root/'backend'),str(root)]
from src.manufacturing_data.cmo import settings
from src.lifesci import envfile
original_settings=settings.load_local_settings
original_env=envfile.load_env_file
def explicit_temp_settings(path=None):
    if path is not None and not Path(path).resolve().is_relative_to(root):
        return original_settings(path)
def explicit_temp_env(path,*args,**kwargs):
    if Path(path).resolve().is_relative_to(root):return []
    return original_env(path,*args,**kwargs)
settings.load_local_settings=explicit_temp_settings
envfile.load_env_file=explicit_temp_env
import pytest
sys.exit(pytest.main(sys.argv[1:]))
