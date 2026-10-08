from benchmark.pharma_simulation.harness import run_validation
from benchmark.pharma_simulation.sme import generate_sme_package
from benchmark.pharma_simulation.validation import validate_dataset, validate_public_facts


if __name__ == "__main__":
    dataset = validate_dataset()
    public = validate_public_facts()
    benchmark = run_validation()
    generate_sme_package()
    print(f"Dataset: {dataset['status']}")
    print(f"Public facts: {public['status']}")
    print(f"Benchmark fingerprint: {benchmark['dataset_fingerprint']}")
