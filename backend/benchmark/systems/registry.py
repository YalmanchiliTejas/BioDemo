from __future__ import annotations

from benchmark.factory.state import FactoryState

from .cmms import CMMS
from .erp import ERP
from .historian import Historian
from .lims import LIMS
from .lms import LMS
from .mes import MES
from .qms import QMS
from .scheduler import Scheduler


class SystemRegistry:
    def __init__(self, state: FactoryState) -> None:
        self.mes = MES(state)
        self.historian = Historian()
        self.lims = LIMS()
        self.qms = QMS()
        self.cmms = CMMS(state)
        self.erp = ERP(state)
        self.scheduler = Scheduler(state)
        self.lms = LMS(state)

    @property
    def names(self) -> tuple[str, ...]:
        return ("MES/eBR", "Historian/SCADA", "LIMS", "QMS", "CMMS", "ERP", "Scheduler", "LMS")
