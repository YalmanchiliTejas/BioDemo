"""Stable backend and adjacent development-runtime locations."""
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
DEFAULT_PRIME_BUNDLE = REPOSITORY_ROOT.parent / "prime-agent-bio"
