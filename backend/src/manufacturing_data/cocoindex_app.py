"""CocoIndex v1 source inventory stage for batch ingestion.

Run with MFG_SOURCE_DIR and MFG_INVENTORY_DIR set, then
``cocoindex update src.manufacturing_data.cocoindex_app``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import cocoindex as coco
from cocoindex.connectors import localfs
from cocoindex.resources.file import FileLike

@coco.fn(memo=True)
async def inventory_file(file: FileLike, outdir: Path) -> None:
    body = await file.read()
    relative = file.file_path.path.as_posix()
    payload = json.dumps({"path":relative,"sha256":hashlib.sha256(body).hexdigest(),
                          "size_bytes":len(body)},sort_keys=True)
    name = hashlib.sha256(relative.encode()).hexdigest() + ".json"
    localfs.declare_file(outdir/name,payload,create_parent_dirs=True)

@coco.fn
async def main(source: Path, outdir: Path) -> None:
    files = localfs.walk_dir(source,recursive=True,live=False)
    await coco.mount_each(inventory_file,files.items(),outdir)

app = coco.App(coco.AppConfig(name="ManufacturingSourceInventory"),main,
               source=Path(os.environ.get("MFG_SOURCE_DIR",".")),
               outdir=Path(os.environ.get("MFG_INVENTORY_DIR","./.manufacturing_inventory")))
