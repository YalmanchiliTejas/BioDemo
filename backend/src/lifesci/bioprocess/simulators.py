"""Runs the corrected PenSim and SMPL models from the physics A/B experiment.

The simulators (PenSimPy and SMPL, both MIT-licensed, from Quartic.ai) need their own Python
environment with a pinned numerical stack and an audited native build, so they run as a separate,
credential-free worker process. The worker executes the experiment's own forward-model entry point
(``benchmarks.external_simulators.forward``) unchanged, so the assistant gets exactly the model
version that was frozen and tested in the experiment.

Configuration:
  LIFESCI_SIMULATOR_PYTHON  interpreter of the simulator environment
                            (default backend/.cache/external-simulators/env/bin/python)
  LIFESCI_SIMULATOR_ROOT    directory holding pensimpy-source/, smpl-source/ and native/
                            (default backend/.cache/external-simulators)
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = BACKEND / '.cache' / 'external-simulators'

MODELS = {
    'pensim': {
        'id': 'pensim.calibrated_fed_batch', 'version': 'operating-challenges-20261028-model-repair-v3',
        'title': 'Industrial penicillin fed-batch (IndPenSim / PenSimPy), source-calibrated',
        'description': 'Mechanistic 33-state fed-batch model with biomass, substrate, oxygen, product and broth '
                       'viscosity. Growth, oxygen-transfer (kLa) and production factors are fitted to the completed '
                       'source batch only. Forecasts penicillin concentration P (g/L) and dissolved oxygen DO2 (mg/L), '
                       'and checks each operating plan against the stated limits.',
        'limitations': [
            'Simulation study, not plant data. The case outcomes come from the same simulator family, so agreement is not external validation.',
            'Qualified for the 96 h window only. The full 230 h batch fails (broth viscosity goes negative) and is not offered.',
            'Fitted factors are effective values; 15 of 48 experiment fits sat near a parameter bound.',
            'In the final A/B experiment the tool reduced PenSim forecast error by 16.5% (95% interval −0.3 to 30.4), short of the 20% bar.',
        ],
    },
    'mab': {
        'id': 'smpl.mab_upstream', 'version': 'operating-challenges-20261028-model-repair-v3',
        'title': 'Antibody upstream perfusion bioreactor with cell separator (SMPL)',
        'description': 'Mechanistic 17-state model of a CHO perfusion reactor and separator (cells, glucose, glutamine, '
                       'lactate, ammonia, antibody, volumes). Starts from the observed state. Forecasts reactor antibody '
                       '(mg/L) and viable cells (cells/L), and checks flow and nutrient plans against the stated limits.',
        'limitations': [
            'Simulation study, not plant data. The tool and the case simulator share equations and the initial state, so close agreement is expected and is not validation.',
            'Same reactor and biology as the source; no scale or site change is modelled.',
            'In the final A/B experiment the tool cut SMPL forecast error by 84% and improved recipe transfer by 17 points, but did not improve operating decisions.',
        ],
    },
}


@dataclass(frozen=True)
class SimulatorWorker:
    python: Path
    root: Path
    timeout_s: float = 90.

    @classmethod
    def from_env(cls) -> 'SimulatorWorker':
        root = Path(os.environ.get('LIFESCI_SIMULATOR_ROOT', DEFAULT_ROOT))
        return cls(Path(os.environ.get('LIFESCI_SIMULATOR_PYTHON', root / 'env' / 'bin' / 'python')), root)

    @property
    def paths(self) -> dict[str, Path]:
        return {'pensim': self.root / 'pensimpy-source', 'smpl': self.root / 'smpl-source', 'native': self.root / 'native'}

    def status(self) -> dict[str, Any]:
        missing = [str(p) for p in [self.python, *self.paths.values()] if not p.exists()]
        return {'available': not missing, 'missing': missing,
                'note': None if not missing else 'Simulator environment not installed; see backend/src/lifesci/bioprocess/simulators.py.'}

    def forward(self, packet: dict[str, Any], action: str) -> dict[str, Any]:
        if not self.status()['available']:
            raise RuntimeError('PenSim/SMPL simulator environment is not installed on this server')
        if action not in packet['allowed_actions'] or action == 'abstain':
            raise ValueError(f'action {action!r} is not an operating plan of this case')
        with tempfile.TemporaryDirectory(prefix='lifesci-sim-') as scratch:
            path = Path(scratch) / 'packet.json'
            path.write_text(json.dumps(packet))
            command = [str(self.python), '-s', '-m', 'benchmarks.external_simulators.forward', '--packet', str(path),
                       '--action', action, *[a for k, p in self.paths.items() for a in (f'--{k}', str(p))]]
            # A minimal environment: no credentials reach the simulator process.
            env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(BACKEND), 'MPLCONFIGDIR': scratch, 'HOME': scratch}
            try:
                done = subprocess.run(command, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=self.timeout_s)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f'simulator exceeded {self.timeout_s:g} s for action {action}') from exc
        if done.returncode:
            raise RuntimeError(f'simulator failed for action {action}: {done.stderr.strip().splitlines()[-1] if done.stderr.strip() else done.returncode}')
        return json.loads(done.stdout)
