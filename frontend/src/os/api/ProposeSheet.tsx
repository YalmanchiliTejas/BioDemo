import { useEffect, useState } from "react";
import { RiAddLine } from "@remixicon/react";
import { Button, Sheet } from "../../lab/ui";
import { errorMessage, type Mission, type ProposalInput } from "./client";
import { useAttemptKey, useConnected } from "./ConnectedWorkspace";
import {
  PROPOSAL_OPERATIONS,
  evidenceBasis,
  evidenceTitle,
  missionBasis,
} from "./mapping";

const blank = {
  operation: PROPOSAL_OPERATIONS[0].id,
  target_system: PROPOSAL_OPERATIONS[0].system,
  target_id: "",
  rationale: "",
  expected_result: "",
  follow_up_measure: "",
};

export function ProposeSheet({
  mission,
  onSaved,
  label = "Propose next step",
}: {
  mission: Mission;
  onSaved: () => void;
  label?: string;
}) {
  const { client, me, evidence, evidenceState, evidenceError, loadEvidence } = useConnected();
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState(blank);
  const [owner, setOwner] = useState(me?.actor_id ?? "");
  const [picked, setPicked] = useState<string[]>([]);
  const [userAuthored, setUserAuthored] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const attempt = useAttemptKey();
  useEffect(() => {
    if (open) void loadEvidence();
  }, [open, loadEvidence]);
  useEffect(() => {
    if (me && !owner) setOwner(me.actor_id);
  }, [me, owner]);
  const set = (key: keyof typeof blank, value: string) =>
    setFields((f) => ({ ...f, [key]: value }));
  const chooseOperation = (id: string) => {
    const previous = PROPOSAL_OPERATIONS.find((o) => o.id === fields.operation);
    const next = PROPOSAL_OPERATIONS.find((o) => o.id === id);
    setFields((f) => ({
      ...f,
      operation: id,
      target_system:
        !f.target_system || f.target_system === previous?.system
          ? (next?.system ?? "")
          : f.target_system,
    }));
  };
  const hasBasis = userAuthored || picked.length > 0;
  const ready =
    !busy &&
    hasBasis &&
    owner.trim() &&
    fields.target_system.trim() &&
    fields.target_id.trim() &&
    fields.rationale.trim() &&
    fields.expected_result.trim();
  const submit = async () => {
    if (!client || !ready) return;
    const basis = userAuthored
      ? missionBasis(mission.mission_id)
      : evidence.filter((r) => picked.includes(r.id)).map(evidenceBasis);
    const siteId = mission.scope.site_ids?.[0] ?? me?.site_ids[0];
    const input: ProposalInput = {
      target_system: fields.target_system.trim(),
      operation: fields.operation,
      target_id: fields.target_id.trim(),
      payload: {},
      basis,
      rationale: fields.rationale.trim(),
      expected_result: fields.expected_result.trim(),
      owner_id: owner.trim(),
      ...(fields.follow_up_measure.trim()
        ? { follow_up_measure: fields.follow_up_measure.trim() }
        : {}),
      ...(siteId ? { site_id: siteId } : {}),
      mission_id: mission.mission_id,
    };
    setBusy(true);
    setError("");
    try {
      await client.propose(input, attempt.keyFor(input));
      attempt.done();
      setOpen(false);
      setFields(blank);
      setPicked([]);
      setUserAuthored(false);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        <RiAddLine size={15} />
        {label}
      </Button>
      <Sheet
        open={open}
        onOpenChange={(next) => {
          if (!busy) setOpen(next);
        }}
        title="Propose a next step"
        description="Saved on the server for review. Nothing is sent or changed in a source system until the required roles approve it."
        footer={
          <>
            <Button onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" disabled={!ready} onClick={() => void submit()}>
              Save proposal
            </Button>
          </>
        }
      >
        <div className="cw-form">
          <p>{mission.objective}</p>
          <label>
            <span>Action</span>
            <select value={fields.operation} onChange={(e) => chooseOperation(e.target.value)}>
              {PROPOSAL_OPERATIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Target system</span>
            <input
              value={fields.target_system}
              maxLength={64}
              placeholder="e.g. MES, LIMS, QMS"
              onChange={(e) => set("target_system", e.target.value)}
            />
          </label>
          <label>
            <span>Target (batch, lot or record ID)</span>
            <input
              value={fields.target_id}
              maxLength={256}
              placeholder="e.g. F-2408"
              onChange={(e) => set("target_id", e.target.value)}
            />
          </label>
          <label>
            <span>Rationale and uncertainty</span>
            <textarea
              rows={3}
              maxLength={2000}
              value={fields.rationale}
              placeholder="Why this step, and what could change the recommendation?"
              onChange={(e) => set("rationale", e.target.value)}
            />
          </label>
          <label>
            <span>Expected result</span>
            <textarea
              rows={2}
              maxLength={2000}
              value={fields.expected_result}
              onChange={(e) => set("expected_result", e.target.value)}
            />
          </label>
          <label>
            <span>Follow-up measure (needed to judge effectiveness later)</span>
            <input
              value={fields.follow_up_measure}
              maxLength={500}
              onChange={(e) => set("follow_up_measure", e.target.value)}
            />
          </label>
          <label>
            <span>Owner</span>
            <input value={owner} maxLength={128} onChange={(e) => setOwner(e.target.value)} />
          </label>
          <fieldset>
            <legend>Basis: what supports this proposal?</legend>
            <label className="cw-check">
              <input
                type="checkbox"
                checked={userAuthored}
                onChange={(e) => {
                  setUserAuthored(e.target.checked);
                  if (e.target.checked) setPicked([]);
                }}
              />
              <span>
                No source evidence (user-authored)
                <small>Recorded as user-authored, not checked against source records.</small>
              </span>
            </label>
            {evidenceState === "loading" && <p className="cw-muted">Loading source records…</p>}
            {evidenceState === "error" && (
              <p className="cw-error" role="alert">
                {evidenceError}
              </p>
            )}
            {evidence.map((record) => (
              <label className="cw-check" key={record.id}>
                <input
                  type="checkbox"
                  checked={picked.includes(record.id)}
                  onChange={(e) => {
                    setUserAuthored(false);
                    setPicked((p) =>
                      e.target.checked ? [...p, record.id] : p.filter((x) => x !== record.id),
                    );
                  }}
                />
                <span>
                  {evidenceTitle(record)}
                  <small>
                    {record.state.source_system} · {record.state.source_record_id}
                    {record.state.site_id ? ` · ${record.state.site_id}` : ""}
                  </small>
                </span>
              </label>
            ))}
            {evidenceState === "ready" && evidence.length === 0 && (
              <p className="cw-muted">No source records are visible to you yet.</p>
            )}
          </fieldset>
          {!hasBasis && <p className="cw-muted">Choose a basis to continue.</p>}
          {error && (
            <p className="cw-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </Sheet>
    </>
  );
}
