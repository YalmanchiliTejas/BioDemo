"""Boot the deployed source tree without the development benchmark package."""
import subprocess
import sys
from pathlib import Path


def test_platform_boot_does_not_require_benchmark():
    result = subprocess.run([sys.executable, '-c', '''
import sys, importlib.abc
class NoBenchmark(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'benchmark' or fullname.startswith('benchmark.'):
            raise ModuleNotFoundError("No module named 'benchmark'")
sys.meta_path.insert(0, NoBenchmark())
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
Platform(RecordStore(), providers={})
'''], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
