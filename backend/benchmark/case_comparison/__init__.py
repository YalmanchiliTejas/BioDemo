"""Evidence-backed benchmark comparison for the two case studies.

The service in this package reads only existing benchmark artifacts
(simulation results, recorded baseline runs, execution logs, and the frozen
case datasets) and shapes them for the comparison dashboard. It never
generates or estimates benchmark values.
"""

from .service import ComparisonService, CASE_ORDER  # noqa: F401
