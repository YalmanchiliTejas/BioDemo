from __future__ import annotations

from pathlib import Path

from benchmarks.common.provenance_validator import validate_mapping
from benchmarks.common.artifact_store import uses_assets


ROOT = Path(__file__).resolve().parent


@uses_assets(ROOT / "raw_package")
def validate_generated_package() -> dict:
    return validate_mapping(ROOT / "raw_package", ROOT / "ground_truth/source_provenance.json")


if __name__ == "__main__":
    result = validate_generated_package()
    print(result)
    if not result["pass"]:
        raise SystemExit(1)
