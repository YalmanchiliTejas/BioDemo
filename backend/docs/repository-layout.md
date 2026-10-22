# Backend reorganization

The Python project root is `backend/`. It contains the API and cloud control
plane, ingestion and manufacturing tools, Prime agent integration and skills,
workflow/state code, evaluation code, tests, infrastructure, scripts, datasets,
saved run state and backend documentation. Python module names stay unchanged.

The React application and its design documentation now live in `frontend/`.
The shared local environment
remains in root `.venv/`; this checkout has a `backend/.venv` convenience link.
For a new environment, install the backend with `pip install -e ./backend` from
the repository root, selecting the required extras.

Root `benchmarks`, `results`, `runs`, `.cache` and `.prime` are compatibility
symlinks into the backend. They preserve absolute references in saved artifacts;
they duplicate no data. Frontend exporters read directly from `backend/`.
Keep the aliases until historical artifact references have been migrated explicitly.
In particular, do not rewrite frozen evaluation records just to remove old paths.

Backend commands run from `backend/`. The isolated cloud Docker build also uses
`backend/` as its context. The CMO Compose build intentionally uses the repository
root as its context because it builds the separate frontend in `frontend/`.
The adjacent Prime checkout is discovered relative to the repository's parent,
with `PRIME_AGENT_BUNDLE_ROOT` retaining priority.

Cleanup removed approximately 262 MiB of reproducible files: the optional
offload virtual environment, Terraform provider downloads (lockfile retained),
Python/test caches, generated egg metadata, Finder metadata, and a byte-identical
copy of `runs/my-comparison`. The original comparison, source datasets, offline
document models, archived evaluations and saved agent work remain intact. The
exact deletion inventory is [repository-cleanup.json](repository-cleanup.json).
The optional offload environment can be recreated using its documented pinned
requirements; it is no longer preinstalled.

Verification after moving:

- Backend suite: 373 passed, 10 skipped, 2 artifact-dependent failures.
- Agent JavaScript suites: all 24 tests passed after relocation.
- The CHO recorded-pilot test needs the already-absent
  `runs/cho-comparison/comparison.json`; that directory was empty before moving.
- The committed-report test compares a stale generated HTML report with current
  evaluation records. The relocated HTML is byte-identical to the original Git
  version. It was preserved rather than regenerating frontend content as part
  of this backend-only change.
- Package imports, CLI help and frontend exporter imports resolve against the
  relocated backend. Cloud and CMO Compose configurations validate; Terraform
  formatting validates. The initial frontend checksum check was unchanged after
  relocation; subsequent unrelated stylesheet work was preserved. No step of
  this reorganization edits frontend source or configuration.
- The cloud control-plane image builds with `backend/` as its context.
