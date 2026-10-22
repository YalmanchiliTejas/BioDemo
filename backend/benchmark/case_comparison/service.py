"""Service layer for the case-comparison dashboard.

Wires the :class:`ArtifactStore` to one case module per case study and exposes
the payload sections the dashboard and API consume. Supporting values come
from recorded artifacts; engineering productivity is computed from measured
effort ledgers and reviewed deliverables.
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from benchmarks.common.engineering_work import HEADLINE, protocol, score
from .scorecard import metric, not_measured, side
from .cho import CASE_ID as CHO_ID, ChoCase
from .fresenius import CASE_ID as FRESENIUS_ID, FreseniusCase
from .sources import REPOSITORY, ArtifactStore

CASE_ORDER = (FRESENIUS_ID, CHO_ID)

SECTION_BUILDERS = (
    "header",
    "scorecard",
    "replay",
    "effort",
    "evidence",
    "differences",
    "issue_chain",
    "presentation",
    "experiments",
    "evaluation",
)


class ComparisonService:
    """Builds comparison payloads for the two case studies from recorded artifacts."""

    def __init__(
        self,
        repository: Path = REPOSITORY,
        *,
        store: ArtifactStore | None = None,
        incident_service: Any | None = None,
    ) -> None:
        self.repository = Path(repository)
        self.store = store or ArtifactStore(self.repository)
        self._incident_service = incident_service
        self._cases: dict[str, Any] = {}
        self._cache: dict[tuple[str, str], Any] = {}

    # ------------------------------------------------------------------ cases
    def _case(self, case_id: str):
        if case_id not in CASE_ORDER:
            raise KeyError(f"unknown case study: {case_id}")
        if case_id not in self._cases:
            if case_id == FRESENIUS_ID:
                self._cases[case_id] = FreseniusCase(
                    self.store, incident_service=self._incident_service,
                )
            else:
                self._cases[case_id] = ChoCase(self.store)
        return self._cases[case_id]

    def cases(self) -> list[dict[str, Any]]:
        """Lightweight index of the available case studies."""
        return [
            {
                "id": case_id,
                "name": case.header().get("name"),
                "title": case.header().get("title"),
                "kind": case.header().get("kind"),
                "dataset_label": case.header().get("dataset", {}).get("label"),
                "question": case.header().get("question"),
            }
            for case_id, case in ((case_id, self._case(case_id)) for case_id in CASE_ORDER)
        ]

    def section(self, case_id: str, name: str) -> Any:
        if name not in SECTION_BUILDERS:
            raise KeyError(f"unknown comparison section: {name}")
        key = (case_id, name)
        if key not in self._cache:
            case = self._case(case_id)
            if name == "evaluation":
                from .evaluation import build_evaluation
                path = self.repository / "results" / case_id / "engineering_work.json"
                ledger = json.loads(path.read_text()) if path.exists() else {"runs": []}
                self._cache[key] = build_evaluation(self.store, case_id, self.section(case_id, "experiments"), ledger)
            elif name == "experiments":
                path = self.repository / "results" / case_id / "engineering_work.json"
                ledger = json.loads(path.read_text()) if path.exists() else {
                    "version": protocol(case_id)["version"], "benchmark": case_id, "runs": [],
                }
                if ledger.get("benchmark") != case_id:
                    raise ValueError("engineering-work ledger belongs to another benchmark")
                self._cache[key] = {**protocol(case_id), **score(ledger), "ledger_path": str(path)}
            else:
                self._cache[key] = getattr(case, name)()
            if name == "presentation":
                presentation = self._cache[key]
                presentation["supporting_headline"] = presentation.get("headline")
                presentation["headline"] = (
                    "Evaluate quality-qualified investigations and total human effort across raw evidence, unfamiliar formats and updates. "
                    "Existing replay, parser and pilot results remain supporting diagnostics."
                )
            if name == "header":
                self._cache[key]["question"] = (
                    "Can the OS produce equivalent or better reviewable investigations with fewer total human-hours, including preparation and verification?"
                    if case_id == "fresenius" else
                    "Can the OS produce equivalent or better validated cultivation comparisons with fewer total human-hours, including preparation and verification?"
                )
            if name == "scorecard":
                experiments = self.section(case_id, "experiments")
                primary = experiments["primary"]
                def measured(workflow):
                    result = primary["sides"][workflow]
                    if result["value"] is None:
                        return not_measured(" ".join(result["issues"]))
                    return side(result["value"], display=f'{result["value"]:.3f} work units/h',
                                classification="observed", unit="work units/person-hour",
                                detail=f'{result["correctly_completed"]}/{result["assigned"]} reviewed deliverables; {result["person_hours"]:.3f} measured person-hours.')
                headline = metric(
                    id="correct_work_per_human_hour", label=HEADLINE, group="Engineering productivity",
                    definition="Accepted end-to-end deliverables / total measured person-hours across all assigned attempts.",
                    traditional=measured("traditional"), ai=measured("ai"),
                    direction="higher" if primary["paired"] else None,
                    note="Experiment A is primary; B and C report robustness separately. Paired deltas require matching assignments, source packages and task specifications.",
                    sources=[{"label": "Engineering work ledger", "path": experiments["ledger_path"]}],
                )
                card = self._cache[key]
                card["supporting_headline"] = card["headline"]
                card["headline"] = [headline]
                card["metrics"].insert(0, headline)
                card["groups"].insert(0, "Engineering productivity")
                card["conclusion"] = (
                    "The effect on correctly completed engineering work per human-hour is not yet established. "
                    if not primary["paired"] else
                    "Experiment A has paired effort logs and reviewed outcomes; B and C report robustness separately. "
                ) + "Supporting results: " + card["conclusion"]
        return self._cache[key]

    def case(self, case_id: str) -> dict[str, Any]:
        """Full payload for one case study (all dashboard sections)."""
        return {
            "id": case_id,
            **{name: self.section(case_id, name) for name in SECTION_BUILDERS},
        }

    def dashboard(self) -> dict[str, Any]:
        return {
            "order": list(CASE_ORDER),
            "cases": self.cases(),
            "sections": list(SECTION_BUILDERS),
        }

    def series(self, cultivation: str, variables: list[str], max_points: int = 240) -> dict[str, Any]:
        """Downsampled aligned trajectories; only the CHO case exposes series data."""
        return self._case(CHO_ID).series(cultivation, variables, max_points)
