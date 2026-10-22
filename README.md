# BioDemo

Backend code, agents, infrastructure, tests, datasets and run artifacts live in
[`backend/`](backend/README.md). The React application, assets, scripts and
design documentation live in [`frontend/`](frontend/README.md).

For a new checkout, create the shared environment and install the backend:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[app,manufacturing-data,cloud-backend]'
cd backend
../.venv/bin/python -m benchmark serve
```

Run backend tests from the same directory with `../.venv/bin/python -m pytest -q`
(with pytest installed in that environment).
See the [cloud deployment runbook](backend/docs/security/cloud-backend.md) for
the DigitalOcean SFO3 setup.

Start the frontend separately:

```sh
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5180/` for the introduction or `/app` for the demo workspace.

`benchmarks`, `results`, `runs`, `.cache` and `.prime` at the repository root are
temporary compatibility symlinks into `backend/`. They preserve existing
historical absolute artifact paths without copies. Frontend export scripts now
read directly from `backend/`.
The shared Python environment remains at `.venv`; `backend/.venv` points to it.
Frontend source and documentation are fully contained in `frontend/`.
