# Deviation workflow discovery

Confirmed with the user during grill-with-docs on 2026-10-23. These are product decisions for the first milestone, not claims of implemented behavior. The governing direction remains [Main_Culture_andETHOS.md](../../Main_Culture_andETHOS.md).

## Confirmed direction

- Coordinate work across existing manufacturing and quality systems, preserving their established responsibilities and official records.
- Prove deviation handling as the first complete capability within a broader pharmaceutical manufacturing product.
- Automatically gather authorized evidence, run checks, prepare drafts, and perform explicitly configured routing. Official quality-record submission and consequential manufacturing actions require separate human authorization.
- Assign each case a named investigation owner and a distinct QA review responsibility; the same person may hold both roles where appropriate.
- Propose prior-investigation reuse with the earlier case summary, similarities, differences, and intended reuse. Require explicit owner approval before acceleration; silence is not approval. Ordinary authorized evidence gathering may continue while waiting.
- Begin the first complete workflow with an existing alarm, quality event, or human report. Expand cross-system pattern detection separately.
- The next milestone is one complete supervised workflow grounded in a representative SOP and corresponding form; the initial demonstration uses explicitly fictional materials as agreed below. Clearly identify simulated connections where real access is unavailable. Demonstrate missing evidence, reviewer corrections, and prior-investigation reuse.

## Additional confirmed requirements

- Procedure inputs may be existing SOP/procedure documents and other relevant materials already available in connected systems, or a procedure map supplied by the user. A procedure map is not a mandatory onboarding prerequisite.
- When evidence is missing or contradictory, continue independent authorized work, identify the gap or conflict, request clarification from the responsible person, and pause dependent conclusions or actions. Do not substitute assumed facts.
- Follow the applicable SOP and configured escalation rules for notification timing. Distinguish initial notification, later findings, and the review package; required notification must not wait for a completed investigation. Resolve unclear notification rules with a human.
- Prepare an editable draft in the organization’s required format, with source evidence for populated fields and unresolved fields explicitly marked. Distinguish observations, calculations, hypotheses, and human decisions; do not fill approved-root-cause fields with unreviewed hypotheses.
- The agent may follow clear instructions in an applicable approved procedure without blanket first-use confirmation. Ambiguity, conflicts, and judgments outside its authority require clarification; consequential actions retain required human authorization.
- User-supplied procedure maps may organize or explain procedures. If a map conflicts with an approved SOP, flag the conflict and pause the affected step. Override requires explicit organizational authorization.
- Use clearly labeled fictional SOPs and corresponding deviation forms for the initial demonstration, then evaluate against authorized customer materials when available. This does not establish correctness against an actual customer procedure.

## Confirmed reference workflow and outputs

- Use recurring microbiological excursions across batches as the initial demonstration scenario, drawing on existing synthetic laboratory, environmental, process, and prior-incident records. Add clearly fictional procedures and corresponding forms. This scenario does not restrict the broader product’s manufacturing scope.
- Evidence preparation includes aligning batch/equipment identifiers, reconciling timestamps and units, checking quality, calculating relevant comparisons, and assembling an event timeline. Preserve original records and expose transformations. Keep unresolved mappings and conflicting records visible.
- The agent may propose evidence-supported explanations. Correlation or similarity alone does not establish a confirmed cause.
- QA receives an editable drafted form, event timeline, source-linked findings, gaps/conflicts, applicable procedure references, prior-investigation reuse approvals, and proposed next steps with owners. Present a concise summary with deeper evidence available.
- QA can return findings or fields for correction. Reassess affected conclusions and drafts after corrections.
- Continue tracking review decisions, assigned actions, and observed outcomes after QA handoff. Only an authorized person or existing system closes the case.
- Preserve distinctions between recommendations, approvals, execution, and observed effectiveness in case history. Unresolved cases may inform retrieval but must not appear as proven successful resolutions.

## Discovery status

The user accepted the final reference-workflow decisions. The broad product interview is complete; no implementation or live deployment is implied by these notes.

Subsequent architecture clarification, 2026-10-23: the user emphasized long-horizon tasks, persistent context, incorporation of the latest information, and proactive suggestions to improve yield and batch correctness. Deviation handling remains a capability within that broader scope. See the [revised architecture proposal](long-horizon-manufacturing-agents.md); its implementation recommendations are not additional confirmed interview decisions.

## Specification work remaining

Turn the agreed behavior into a buildable specification with explicit simulated integration boundaries, fictional roles and escalation rules, procedure/form fixtures, persisted case transitions, evidence and permission checks, correction behavior, and acceptance scenarios. Technical choices should follow inspection of existing foundations; these are implementation tasks, not silently settled architecture decisions.

Use observable measures aligned with the governing pillars: manual preparation and time to the first useful package; source/transform traceability and reviewer correction effort; completion of review/action handoffs and recorded outcomes; setup and integration burden. Set numerical targets only with an appropriate baseline; none have been validated here.

Customer-specific procedures, authority assignments, access permissions, notification rules, and integration configuration must be resolved before a real deployment. The fictional demonstration does not establish customer-procedure correctness, manufacturing effectiveness, regulatory compliance, or live integration readiness.
