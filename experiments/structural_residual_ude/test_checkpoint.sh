#!/usr/bin/env bash
# Run with the experiment's Python environment activated.
set -euo pipefail

usage() {
    echo "Usage: ${0##*/} JOB_ID|RUN_DIR"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi
if [[ "$#" != 1 ]]; then
    usage >&2
    exit 2
fi

run_dir="$1"
if [[ "$run_dir" =~ ^[0-9]+$ ]]; then
    if [[ -z "${BIOCORE_RUN_ROOT:-}" ]]; then
        : "${SCRATCH:?Set SCRATCH or BIOCORE_RUN_ROOT when using a job ID}"
    fi
    run_dir="${BIOCORE_RUN_ROOT:-${SCRATCH%/}/biocore-lyo}/run-$run_dir"
fi
checkpoint="$run_dir/best.safetensors"
if [[ ! -f "$checkpoint" ]]; then
    echo "Checkpoint not found: $checkpoint" >&2
    exit 1
fi

exec python -m biocore.method_a.evaluate "$checkpoint" --output "$run_dir/evaluation"
