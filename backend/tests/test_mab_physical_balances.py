"""Inventory/clock checks independent of the integration wrapper."""
from pathlib import Path
import numpy as np
import pytest
from benchmarks.external_simulators.upstream import read_mab

SOURCE=Path('/private/tmp/biodemo-smpl-source')
pytestmark=pytest.mark.skipif(not SOURCE.exists(),reason='Pinned SMPL equations required')

@pytest.mark.parametrize('factor',[.8,.9,1.])
def test_external_product_inventory_balance_and_minutes(factor):
    model,x,u=read_mab(SOURCE);u=u.copy();u[:4]*=factor
    # Non-steady inventories and volumes expose missing internal-flow cancellation.
    x=x.copy();x[6]*=.7;x[14]*=1.2;x[7]*=.95;x[15]*=1.05
    dx=np.asarray(model.xdot(x,u),dtype=float)
    inventory_rate=dx[6]*x[7]+x[6]*dx[7]+dx[14]*x[15]+x[14]*dx[15]
    production_mg_per_min=(6.59e-10/60.)*x[0]*x[7]
    external_harvest_mg_per_min=x[14]*u[3]
    assert inventory_rate==pytest.approx(production_mg_per_min-external_harvest_mg_per_min,rel=1e-11)
    assert dx[7]+dx[15]==pytest.approx(u[0]-u[3],abs=1e-10)
