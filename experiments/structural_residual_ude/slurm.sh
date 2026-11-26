#!/usr/bin/env bash
# Run with: ./slurm.sh --simulation-dir /path/to/splits --smoke
# Set SBATCH_ACCOUNT, SBATCH_PARTITION, or SBATCH_TIMELIMIT to override site defaults.

#SBATCH --job-name=biocore-lyo
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --open-mode=append
#SBATCH --account=gpu

set -euo pipefail

if [[ -z "${BIOCORE_RUN_ROOT:-}" ]]; then
    : "${SCRATCH:?Set SCRATCH or BIOCORE_RUN_ROOT to shared storage.}"
    BIOCORE_RUN_ROOT="${SCRATCH%/}/biocore-lyo"
fi
mkdir -p -- "$BIOCORE_RUN_ROOT"
BIOCORE_RUN_ROOT="$(cd -- "$BIOCORE_RUN_ROOT" && pwd)"
export BIOCORE_RUN_ROOT

# Slurm runs a spool copy, so set the working directory at submission.
if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    experiment_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    echo "Slurm logs and run directories: $BIOCORE_RUN_ROOT"
    exec sbatch --chdir="$experiment_dir" --export=ALL \
        --output="$BIOCORE_RUN_ROOT/slurm-%j.out" --error="$BIOCORE_RUN_ROOT/slurm-%j.err" \
        "$experiment_dir/slurm.sh" "$@"
fi

module load anaconda
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate rl
python_bin="$(command -v python)"
"$python_bin" -m pip install -e .

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
run_dir="$BIOCORE_RUN_ROOT/run-$SLURM_JOB_ID"
if [[ "${SLURM_RESTART_COUNT:-0}" != 0 ]]; then
    run_dir+="-restart-$SLURM_RESTART_COUNT"
fi
echo "Job $SLURM_JOB_ID on $(hostname)"
echo "Default artifact directory: $run_dir"
exec srun "$python_bin" -u -m biocore.method_a.train --output "$run_dir" "$@"
