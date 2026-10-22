from benchmark.pharma_simulation.validation import validate_dataset


if __name__ == "__main__":
    result = validate_dataset()
    print(f"DATASET VALIDATION: {result['status']}")
    for issue in result["issues"]:
        print(f"- {issue}")

