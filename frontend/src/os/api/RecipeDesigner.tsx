import { useState } from "react";
import { Field, JsonField, SuitePanel, useRecords, useSuite } from "./suite-tools";
import type { SuiteRecord } from "./client";

type Step = {
  step_id: string; title: string; kind: string; depends_on: string[]; parallel_group?: string;
  parameters: { name: string; unit: string; low?: number; high?: number; type?: string }[];
  calculation?: { name: string; expr: string; unit: string };
  branch?: { condition: string; true_next: string; false_next: string };
  required_signatures?: string[]; resources?: Record<string, unknown>; enforcement?: Record<string, boolean>;
  [key: string]: unknown;
};
type Definition = { steps: Step[]; constants?: Record<string, number>; template_params?: unknown[]; [key: string]: unknown };
const fresh = (n: number): Step => ({ step_id: `step${n}`, title: "", kind: "instruction", depends_on: [], parameters: [] });
export function RecipeDesigner() {
  const s = useSuite();
  const { records, error } = useRecords("procedure", s.version);
  const [id, setId] = useState(""); const [name, setName] = useState("");
  const [site, setSite] = useState(s.me.site_ids[0] ?? "");
  const [global, setGlobal] = useState(false);
  const [category, setCategory] = useState("recipe");
  const [definition, setDefinition] = useState<Definition>({ steps: [fresh(1)] });
  const [revision, setRevision] = useState<number | null>(null);
  const [previewParams, setPreviewParams] = useState({});
  const [loaded, setLoaded] = useState(0);
  const [adaptSite, setAdaptSite] = useState(""); const [overrides, setOverrides] = useState({});
  function load(r: SuiteRecord) {
    setId(r.id); setName(String(r.state.name)); setCategory(String(r.state.category)); setSite(String(r.state.site_id ?? ""));
    setGlobal(!r.state.site_id); setRevision(r.revision); setDefinition(structuredClone(r.state.draft) as Definition); setLoaded((v) => v + 1);
  }
  const change = (i: number, patch: Partial<Step>) => setDefinition((d) => ({ ...d, steps: d.steps.map((st, j) => j === i ? { ...st, ...patch } : st) }));
  return <SuitePanel state={s}><div className="suite-columns"><section><form onSubmit={(e) => { e.preventDefault(); void s.run(async () => {
    const body = revision ? { definition, expected_revision: revision } : { procedure_id: id, name, site_id: global ? null : site, category, definition };
    const r = await s.command<{ revision: number }>(revision ? `/v1/procedures/${encodeURIComponent(id)}/draft` : "/v1/procedures", body);
    setRevision(r.revision); return r;
  }); }}>
    <h2>Recipe and method designer</h2><div className="suite-fields"><Field label="Procedure ID" value={id} onChange={setId} /><Field label="Name" value={name} onChange={setName} />
    <label>Category<select value={category} onChange={(e) => setCategory(e.target.value)}>{["recipe", "work_instruction", "lab_method"].map((v) => <option key={v}>{v}</option>)}</select></label>
    <Field label="Site" value={site} onChange={setSite} required={!global} /></div>
    <label><span><input type="checkbox" checked={global} disabled={revision !== null} onChange={(e) => setGlobal(e.target.checked)} /> Global template</span></label>
    {definition.steps.map((st, i) => <fieldset key={`${loaded}:${i}`}><legend>{st.step_id}</legend>
      <Field label="Instruction" value={st.title} onChange={(title) => change(i, { title })} />
      <label>Step kind<select value={st.kind} onChange={(e) => change(i, { kind: e.target.value })}>{["instruction", "data_entry", "calculation", "material_check", "equipment_check", "signature", "sample"].map((v) => <option key={v}>{v}</option>)}</select></label>
      <label>Dependencies<select multiple value={st.depends_on} onChange={(e) => change(i, { depends_on: Array.from(e.target.selectedOptions, (o) => o.value) })}>{definition.steps.filter((x) => x.step_id !== st.step_id).map((x) => <option key={x.step_id}>{x.step_id}</option>)}</select></label>
      <Field label="Parallel group (optional)" value={st.parallel_group ?? ""} required={false} onChange={(parallel_group) => change(i, { parallel_group })} />
      {(st.parameters ?? []).map((p, j) => <div className="suite-fields" key={j}>
        {(["name", "unit", "low", "high"] as const).map((k) => <Field key={k} label={`Parameter ${j + 1} ${k}`} value={String(p[k] ?? "")} type={k === "low" || k === "high" ? "number" : "text"} required={k === "name" || k === "unit" || category === "lab_method"} onChange={(value) => change(i, { parameters: st.parameters.map((x, n) => n === j ? { ...x, [k]: k === "low" || k === "high" ? value === "" ? undefined : Number(value) : value } : x) })} />)}
        <button type="button" onClick={() => change(i, { parameters: st.parameters.filter((_, n) => n !== j) })}>Remove parameter {j + 1}</button>
      </div>)}
      <button type="button" onClick={() => change(i, { parameters: [...(st.parameters ?? []), { name: "", unit: "" }] })}>Add parameter</button>
      <details><summary>Calculation</summary>{(["name", "expr", "unit"] as const).map((k) => <Field key={k} label={`Calculation ${k}`} required={!!st.calculation || st.kind === "calculation"} value={st.calculation?.[k] ?? ""} onChange={(v) => change(i, { calculation: { name: "", expr: "", unit: "", ...st.calculation, [k]: v } })} />)}<button type="button" onClick={() => change(i, { calculation: undefined })}>Remove calculation</button></details>
      <details><summary>Conditional branch</summary><Field label="Condition expression" required={false} value={st.branch?.condition ?? ""} onChange={(condition) => change(i, { branch: { true_next: "", false_next: "", ...st.branch, condition } })} />
        {(["true_next", "false_next"] as const).map((k) => <label key={k}>{k}<select value={st.branch?.[k] ?? ""} onChange={(e) => change(i, { branch: { condition: "", true_next: "", false_next: "", ...st.branch, [k]: e.target.value } })}><option value="">Choose step…</option>{definition.steps.filter((x) => x.step_id !== st.step_id).map((x) => <option key={x.step_id}>{x.step_id}</option>)}</select></label>)}
        <button type="button" onClick={() => change(i, { branch: undefined })}>Remove branch</button>
      </details>
      <details><summary>Signatures, guardrails and resources</summary>
        <label>Required signatures<select multiple value={st.required_signatures ?? []} onChange={(e) => change(i, { required_signatures: Array.from(e.target.selectedOptions, (o) => o.value) })}>{["performed", "verified", "reviewed", "approved"].map((v) => <option key={v}>{v}</option>)}</select></label>
        <JsonField label="Resource requirements" value={st.resources ?? {}} onChange={(resources) => change(i, { resources })} />
        <JsonField label="Enforcement rules" value={st.enforcement ?? {}} onChange={(enforcement) => change(i, { enforcement })} />
      </details>
      <button type="button" onClick={() => setDefinition((d) => ({ ...d, steps: d.steps.filter((_, j) => j !== i) }))}>Remove step</button>
    </fieldset>)}
    <button type="button" onClick={() => { let n = definition.steps.length + 1; while (definition.steps.some((st) => st.step_id === `step${n}`)) n++; setDefinition((d) => ({ ...d, steps: [...d.steps, fresh(n)] })); }}>Add step</button>
    <details key={loaded}><summary>Templates and full definition</summary><JsonField label="Template parameters" value={definition.template_params ?? []} onChange={(template_params) => setDefinition((d) => ({ ...d, template_params }))} />
      <JsonField label="Constants" value={definition.constants ?? {}} onChange={(constants) => setDefinition((d) => ({ ...d, constants }))} />
      <JsonField label="Full definition (advanced)" value={definition} onChange={(v) => { if (!v || !Array.isArray(v.steps) || v.steps.some((st: Step) => !st || typeof st.step_id !== "string" || !Array.isArray(st.depends_on ?? []) || !Array.isArray(st.parameters ?? []))) throw Error("Invalid definition"); setDefinition(v); }} /></details>
    <JsonField label="Preview parameter values" value={previewParams} onChange={setPreviewParams} />
    <div className="suite-buttons"><button type="button" onClick={() => void s.run(() => s.command("/v1/procedures/preview", { definition, params: previewParams }))}>Validate and preview</button><button>Save {revision ? "new draft revision" : "draft"}</button>
    <button type="button" onClick={() => { setId(""); setName(""); setRevision(null); setDefinition({ steps: [fresh(1)] }); setLoaded((n) => n + 1); }}>New procedure</button></div>
  </form>
  <form onSubmit={(e) => { e.preventDefault(); void s.run(() => s.command(`/v1/procedures/${encodeURIComponent(id)}/adapt`, { revision: records.find((r) => r.id === id)?.state.effective_revision, site_id: adaptSite, overrides })); }}><h2>Adapt a published global template</h2><Field label="Receiving site" value={adaptSite} onChange={setAdaptSite} /><JsonField label="Allowed parameter overrides" value={overrides} onChange={setOverrides} /><button disabled={!id}>Create site variant for review</button></form>
  </section><section><h2>Saved procedures</h2>{error && <p role="alert">{error}</p>}{records.map((r) => <article className="suite-result" key={r.id}><h3>{String(r.state.name)}</h3><p>{String(r.state.status)} · revision {r.revision}</p><div className="suite-buttons"><button onClick={() => load(r)}>Edit draft</button><button onClick={() => void s.run(() => s.client.submitProcedure(r.id, "Review revised procedure"))}>Submit for review</button>{r.state.pending_submission != null && <button onClick={() => void s.run(() => s.client.publishProcedure(r.id, (r.state.pending_submission as { proposal_id: string }).proposal_id))}>Publish after approval</button>}</div></article>)}</section></div></SuitePanel>;
}
