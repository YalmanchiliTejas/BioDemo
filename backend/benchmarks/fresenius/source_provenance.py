from __future__ import annotations

from pathlib import Path

from benchmarks.common.provenance_validator import validate_mapping


ROOT = Path(__file__).resolve().parent


def validate_generated_package() -> dict:
    return validate_mapping(ROOT / "raw_package", ROOT / "ground_truth/source_provenance.json")


if __name__ == "__main__":
    result = validate_generated_package()
    print(result)
    if not result["pass"]:
        raise SystemExit(1)
