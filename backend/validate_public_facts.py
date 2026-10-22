from benchmark.pharma_simulation.validation import validate_public_facts


if __name__ == "__main__":
    result = validate_public_facts()
    print(f"PUBLIC FACT CONSISTENCY: {result['status']}")
    for failure in result["failures"]:
        print(f"- {failure}")
