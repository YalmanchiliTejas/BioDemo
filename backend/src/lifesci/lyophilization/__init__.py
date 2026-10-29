"""Independent, unqualified primary-drying calculations; no agent dependency."""

from .model import MODEL_VERSION, simulate, uncertainty

__all__ = ["MODEL_VERSION", "simulate", "uncertainty"]
