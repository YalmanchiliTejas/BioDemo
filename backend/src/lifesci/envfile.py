"""Read local ``.env`` files without adding a dependency.

Only ``KEY=VALUE`` lines are understood. Blank lines and lines starting with
``#`` are ignored, an optional ``export`` prefix is accepted, and values may be
single- or double-quoted. Real environment variables take precedence: a value
from the file is applied only when the key is not already set (unless
``override=True``).

Variable expansion, command substitution and multi-line values are deliberately
not supported; local configuration should stay simple and predictable.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import MutableMapping

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_env(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` text into a mapping, preserving file order."""
    values: dict[str, str] = {}
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not _KEY.match(key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            quote, value = value[0], value[1:-1]
            if quote == '"':
                value = (value.replace("\\n", "\n").replace("\\t", "\t")
                              .replace('\\"', '"').replace("\\\\", "\\"))
        else:
            # An unquoted value ends at a whitespace-preceded comment marker.
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def load_env_file(path: str | Path, environ: MutableMapping[str, str] | None = None, *,
                  override: bool = False) -> list[str]:
    """Apply a local env file; return the keys that were set.

    A missing file is not an error: the process may be configured entirely by
    its real environment. Existing environment variables win unless ``override``.
    """
    target = os.environ if environ is None else environ
    source = Path(path).expanduser()
    if not source.is_file():
        return []
    applied: list[str] = []
    for key, value in parse_env(source.read_text(encoding="utf-8")).items():
        if override or key not in target:
            target[key] = value
            applied.append(key)
    return applied
