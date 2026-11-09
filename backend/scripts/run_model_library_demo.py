"""Isolated synthetic model-library API; never reads production configuration."""

import argparse
import json
import os
from pathlib import Path
from src.lifesci.container import Platform
from src.lifesci.store import RecordStore
from src.lifesci.devseed import seed, TENANT
from src.lifesci.api import create_app
from src.lifesci.process_models.examples import examples
from src.lifesci.chemical_reactor.demo import example
from src.lifesci.fermentation.data import project


def seed_library(p):
    seed(p)
    ctx = p.identity.context_for(TENANT, "priya")
    service = p.process_models.analysis
    configs = examples() | {
        "chemical.parallel_batch": example(),
        "fermentation.oxygen_transfer": {"project": project("sulfolobus"), "assumptions": {}},
        "fermentation.pressure_cost": {"project": project("pichia"), "assumptions": {}},
    }
    contexts = []
    for mid, c in configs.items():
        original = p.evidence.ingest(
            ctx,
            source_system="pharmaceutical-synthetic-demo",
            source_record_id=mid,
            content=json.dumps(
                {"config": c, "evidence_classification": "synthetic_assumption"}, sort_keys=True
            ).encode(),
            media_type="application/json",
            site_id="NF1",
            event_time=None,
            metadata={"synthetic": True},
        )
        existing = [
            r
            for r in p.store.read().list(TENANT, "physical_analysis_context")
            if r.state.get("model_id") == mid
            and r.state.get("status") == "current"
            and r.state["input_bundle"]["config"] == c
        ]
        if existing:
            contexts.append(existing[-1].id)
            continue
        contexts.append(
            service.create_configuration(
                ctx,
                {
                    "model_id": mid,
                    "site_id": "NF1",
                    "label": "SYNTHETIC · " + mid,
                    "config": c,
                    "classification": "synthetic_assumption",
                    "assumptions": ["Authored executable example, not measured customer characterization"],
                    "basis": [
                        {
                            "kind": "evidence",
                            "id": original["evidence_id"],
                            "revision": original["revision"],
                            "site_id": "NF1",
                        }
                    ],
                },
            )["id"]
        )
    return contexts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8197)
    args = parser.parse_args()
    os.environ.setdefault("LIFESCI_CORS_ORIGINS", "http://127.0.0.1:5189,http://127.0.0.1:5180")
    os.environ["LIFESCI_AUTH_MODE"] = "development"
    os.environ["MODAL_EMBEDDINGS_URL"] = ""
    p = Platform(RecordStore(str(args.db)), providers={})
    records = seed_library(p)
    print(
        json.dumps(
            {
                "synthetic_contexts": len(records),
                "tenant": TENANT,
                "actor": "priya",
                "site": "NF1",
                "provider_inference": "disabled",
                "database": str(args.db),
            }
        ),
        flush=True,
    )
    import uvicorn

    uvicorn.run(create_app(p), host="127.0.0.1", port=args.port)
