"""Data-only weights with a verified configuration, manifest, and provenance."""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file

from .config import DTYPE, LyoModelConfig, ModelConfig
from .model import HybridBioprocessUDE, HybridLyophilizationUDE


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_artifact(model: HybridBioprocessUDE | HybridLyophilizationUDE, path: Path, metadata: dict) -> None:
    if not isinstance(model, (HybridBioprocessUDE, HybridLyophilizationUDE)):
        raise ValueError("Unsupported model type")
    if any(t.dtype != DTYPE or not torch.isfinite(t).all() for t in model.state_dict().values()):
        raise ValueError("Artifact tensors must be finite float64")
    path = Path(path)
    if path.suffix != ".safetensors":
        raise ValueError("Weights must use .safetensors")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".safetensors.tmp")
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}, str(tmp))
    tmp.replace(path)
    config_path = path.with_suffix(".json")
    write_json(config_path, {
        "schema_version": 2, "dtype": "float64", "device": "cpu",
        "model_type": "lyophilization" if isinstance(model, HybridLyophilizationUDE) else "fermentation",
        "units": ({"time": "s", "temperature": "K", "pressure": "Pa", "length": "m"}
                  if isinstance(model, HybridLyophilizationUDE) else {"time": "h"}),
        "model": model.config.model_dump(), "weights_sha256": sha256(path),
        "versions": {"python": platform.python_version(), **{
            name: importlib.metadata.version(name)
            for name in ("torch", "torchode", "numpy", "safetensors", "pydantic")}},
        "metadata": metadata,
    })
    write_json(path.with_suffix(".sha256.json"),
               {path.name: sha256(path), config_path.name: sha256(config_path)})


def load_artifact(path: Path) -> tuple[HybridBioprocessUDE | HybridLyophilizationUDE, dict]:
    path = Path(path)
    config_path = path.with_suffix(".json")
    manifest = json.loads(path.with_suffix(".sha256.json").read_text())
    for candidate in (path, config_path):
        if manifest.get(candidate.name) != sha256(candidate):
            raise ValueError(f"SHA-256 mismatch: {candidate.name}")
    document = json.loads(config_path.read_text())
    if document["schema_version"] not in (1, 2) or document["dtype"] != "float64":
        raise ValueError("Unsupported artifact schema or dtype")
    if document["weights_sha256"] != sha256(path):
        raise ValueError("Weights do not match config")
    model_type = document.get("model_type") if document["schema_version"] == 2 else "fermentation"
    if model_type == "lyophilization":
        if document["units"] != {"time": "s", "temperature": "K", "pressure": "Pa", "length": "m"}:
            raise ValueError("Unsupported lyophilization units")
        model = HybridLyophilizationUDE(LyoModelConfig.model_validate(document["model"]))
    elif model_type == "fermentation":
        model = HybridBioprocessUDE(ModelConfig.model_validate(document["model"]))
    else:
        raise ValueError("Unsupported artifact model_type")
    tensors = load_file(str(path), device="cpu")
    if any(t.dtype != DTYPE for t in tensors.values()):
        raise ValueError("Artifact contains non-float64 tensors")
    model.load_state_dict(tensors, strict=True)
    if isinstance(model, HybridBioprocessUDE) and not torch.equal(model.state_scale, torch.tensor(model.config.state_scale, dtype=DTYPE)):
        raise ValueError("Config/weights scaling mismatch")
    if not all(torch.isfinite(t).all() for t in model.state_dict().values()):
        raise ValueError("Artifact contains nonfinite weights")
    model.eval().requires_grad_(False)
    return model, document
