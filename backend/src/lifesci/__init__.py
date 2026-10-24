"""Life-sciences platform domain package.

Implements the capability plan in ``docs/product/life-sciences-platform``:
shared contracts (identity, ownership, versioned records, evidence lineage),
the model gateway (deterministic-first routing with budgets and metering),
persistent missions, proposal/approval/intent/outcome actions, and the
procedure, execution, laboratory, integration, scientific, network,
collaboration and assurance modules.

Existing systems remain systems of record unless ownership is explicitly
assigned (ADR 0001). Domain state is versioned with an append-only audit and a
transactional outbox (ADR 0002). Missions persist independently of any model
session (ADR 0003).
"""

from .ids import new_id, utc_now, content_hash  # noqa: F401
from .store import RecordStore, ConflictError  # noqa: F401
