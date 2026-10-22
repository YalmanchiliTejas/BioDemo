from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.pharma_simulation.generator import DEFAULT_OUTPUT, generate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate the seeded pharmaceutical simulation dataset.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = generate(args.seed, args.output)
    print(f"Generated {result['counts']['batches']} batches")
    print(f"Fingerprint: {result['dataset_fingerprint']}")
