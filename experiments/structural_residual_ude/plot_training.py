"""Plot the loss and learning rates from an experiment's training metrics."""

import argparse
import csv
from pathlib import Path


def plot_training(metrics_path: Path, output: Path) -> None:
    with metrics_path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"epoch", "phase", "train_loss", "val_loss", "physics_lr", "residual_lr"}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{metrics_path} is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"No completed epochs in {metrics_path}.")

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator

    epochs = [int(row["epoch"]) for row in rows]
    figure = Figure(figsize=(9, 6), layout="constrained")
    FigureCanvasAgg(figure)
    loss, rates = figure.subplots(2, 1, sharex=True)
    marker = "o" if len(rows) == 1 else None
    loss.plot(epochs, [float(row["train_loss"]) for row in rows], label="Training", marker=marker)
    loss.plot(epochs, [float(row["val_loss"]) for row in rows], label="Validation", marker=marker)
    loss.set_title("Training and validation loss", loc="left")
    loss.set_ylabel("Total loss")

    rates.plot(epochs, [float(row["physics_lr"]) for row in rows], label="Physics", marker=marker)
    rates.plot(epochs, [float(row["residual_lr"]) for row in rows], label="Residual", marker=marker)
    rates.set_title("Adam learning rates", loc="left")
    rates.set_yscale("log")
    rates.set_ylabel("Learning rate (log scale)")
    rates.set_xlabel("Epoch")
    rates.xaxis.set_major_locator(MaxNLocator(integer=True))

    hybrid_start = next((epoch for epoch, row in zip(epochs, rows) if row["phase"] == "hybrid"), None)
    if rows[0]["phase"] == "physics_only" and hybrid_start is not None:
        loss.axvline(hybrid_start, color="0.4", linestyle="--", label="Hybrid training starts")
        rates.axvline(hybrid_start, color="0.4", linestyle="--")
    for axis in (loss, rates):
        axis.grid(axis="y", alpha=0.25)
        axis.legend()

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Directory containing training_metrics.csv")
    parser.add_argument("--output", type=Path, help="Image path (default: RUN_DIR/training_curves.png)")
    args = parser.parse_args()
    output = args.output or args.run_dir / "training_curves.png"
    if not output.suffix:
        output = output.with_suffix(".png")
    try:
        plot_training(args.run_dir / "training_metrics.csv", output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    except ModuleNotFoundError as error:
        if error.name != "matplotlib":
            raise
        parser.error("Install Matplotlib with python -m pip install matplotlib")
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
