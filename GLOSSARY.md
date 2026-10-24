# BioDemo

Shared language for pharmaceutical manufacturing work coordinated across existing systems.

## Language

**AI operating system**:
The product layer that coordinates manufacturing and quality work across existing systems while those systems retain their established responsibilities and official records.
_Avoid_: Replacement system of record

**Deviation case**:
The coordinated work concerning a potential or established manufacturing deviation, including its evidence, investigation, review, actions, and follow-up. A case can begin with a signal before a deviation has been formally confirmed.

**Prior investigation**:
A recorded earlier investigation with its evidence, findings, review history, actions, and observed outcomes where available. Similarity to a current case does not establish that its conclusions apply.

**Prior-investigation reuse**:
Using an earlier investigation to accelerate work on a current case, subject to checking its applicability. The investigation owner reviews the proposed prior investigation’s summary, relevance, differences, and intended reuse, and explicitly approves reuse before acceleration begins.

**Investigation owner**:
The named person responsible for supervising the agent’s work on a deviation case and approving proposed reuse of prior investigations.

**QA reviewer**:
The person responsible for quality review of a deviation case. This responsibility is distinct from investigation ownership, although one person may hold both roles where appropriate.

**Procedure map**:
A structured representation of procedural steps and their relationships, which may be supplied by a user. Its authority depends on organizational approval; supplying a map alone does not authorize it to override an approved SOP.

**QA review package**:
The material assembled for quality review of a deviation case: its drafted form, event timeline, source-linked findings, evidence gaps and conflicts, applicable procedures, prior-investigation reuse approvals, and proposed next steps with owners.

**Manufacturing mission**:
An ongoing, owned objective concerning manufacturing work, with a defined scope, constraints, unfinished tasks, and decisions. A mission may span a batch, campaign, equipment concern, or technology transfer and may contain multiple deviation cases.

**Recommendation**:
A proposed next step with its supporting evidence, assumptions, intended outcome, and responsible owner. A recommendation is distinct from its approval, execution, and observed effectiveness.

**Action intent**:
The queued, approved instruction to perform one exact version of a recommendation in its owning system. An intent is checked again for current evidence, authority and ownership immediately before it is sent, and its delivery can be confirmed, failed or unknown.
_Avoid_: Treating approval as execution

**Qualified route**:
A model assignment for one task kind that a recorded evaluation has shown to meet that task's quality thresholds. Tasks without a qualified route are not sent to a model by default.

**Transfer package**:
The versioned process knowledge, procedures, parameters, resource mappings, and supporting evidence shared with a receiving site or partner for technology transfer. Receipt of the package does not establish readiness to execute the process.
