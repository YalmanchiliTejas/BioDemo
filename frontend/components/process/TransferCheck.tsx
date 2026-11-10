'use client';
import { Pill, type Tone } from '@/components/ui';

type Capability = { capability: string; unit?: string; status: string; receiving_need?: number; receiving_capacity?: number;
  receiving_margin_fraction?: number | null; how?: string; violations?: string[]; reason?: string };
type Check = { metric: string; status: string; unit?: string; operator?: string; limit?: number; margin?: number;
  receiver_estimate?: number; receiver_range?: [number, number]; difference_range?: [number, number]; reason?: string };
type Change = { input: string; sending: number | null; receiving: number | null; relative_change: number | null };
type Tolerance = { path: string; unit: string; low: number; high: number; basis: string; source: string };
export type TransferOutput = { conclusion: string; checks: Check[]; what_changes?: Change[]; tolerances?: Tolerance[];
  equipment_capability?: { checks: Capability[]; family_check: string; scope: string } };

// Each verdict says what it rests on: a person must see at a glance whether it is calibrated, model-based or neither.
const STATUS: Record<string, { label: string; tone: Tone; basis: string }> = {
  conditional_pass: { label: 'Pass', tone: 'success', basis: 'Calibrated on real batches' },
  fails_criterion: { label: 'Fails', tone: 'critical', basis: 'Calibrated on real batches' },
  model_based_pass: { label: 'Pass (model-based)', tone: 'success', basis: 'Physics over the stated tolerances; not calibrated' },
  model_based_fail: { label: 'Fails (model-based)', tone: 'critical', basis: 'Physics model; not calibrated' },
  at_risk: { label: 'At risk', tone: 'warning', basis: 'Fails somewhere within the stated tolerances' },
  inconclusive: { label: 'Inconclusive', tone: 'warning', basis: 'Range straddles the limit' },
  indicative_only: { label: 'Indicative only', tone: 'muted', basis: 'Single estimate; not evidence either way' },
  withheld: { label: 'Withheld', tone: 'muted', basis: 'The model cannot answer this' },
};
const CONCLUSION: Record<string, [string, Tone]> = {
  criteria_not_met: ['Criteria not met', 'critical'], at_risk_within_tolerances: ['At risk within tolerances', 'warning'],
  conditional_model_criteria_met: ['Criteria met (calibrated)', 'success'], model_based_criteria_met: ['Criteria met (model-based)', 'success'],
  inconclusive_uncertainty: ['Inconclusive: needs a measurement', 'warning'], withheld_missing_quality_evidence: ['Withheld: missing quality evidence', 'muted'],
};
const METRIC: Record<string, string> = { product_yield_fraction: 'Desired-product yield', impurity_fraction: 'Impurity' };
const INPUT = (path: string) => path.split('.').pop()!.replace(/_(m3|m2|k|w_m2_k|s|j_mol|kg_m3)$/, '').replaceAll('_', ' ');

const num = (v: number | null | undefined, unit = '') => v == null ? '—'
  : unit === 'fraction' ? `${(100 * v).toFixed(1)} %` : unit === 'W' ? `${(v / 1000).toFixed(1)} kW` : `${+v.toPrecision(3)} ${unit}`.trim();

export function TransferCheck({ output }: { output: TransferOutput }) {
  const [conclusion, tone] = CONCLUSION[output.conclusion] ?? [output.conclusion.replaceAll('_', ' '), 'neutral' as Tone];
  const capability = output.equipment_capability?.checks ?? [];
  return <div className="space-y-4" aria-label="Pre-transfer check">
    <div className="flex flex-wrap items-center gap-2"><h4 className="text-sm font-medium">Pre-transfer check</h4><Pill tone={tone}>{conclusion}</Pill>
      <span className="text-xs text-text-secondary">Draft for engineering review · not a transfer approval</span></div>

    {!!capability.length && <div className="overflow-auto"><table className="w-full text-left text-xs">
      <caption className="mb-2 text-left font-medium">Can the receiving equipment do what the process needs?</caption>
      <thead><tr className="text-text-secondary"><th className="py-1 pr-3">Need</th><th className="pr-3">Required</th><th className="pr-3">Available</th><th className="pr-3">Margin</th><th>Status</th></tr></thead>
      <tbody>{capability.map(c => <tr key={c.capability} className="border-t border-border-hairline align-top">
        <td className="py-2 pr-3">{c.capability}{c.how && <p className="mt-1 text-text-tertiary">{c.how}</p>}
          {!!c.violations?.length && <p className="mt-1 text-status-critical">Stops: {c.violations.map(v => v.replaceAll('_', ' ')).join(', ')}</p>}</td>
        <td className="pr-3">{num(c.receiving_need, c.unit)}</td><td className="pr-3">{num(c.receiving_capacity, c.unit)}</td>
        <td className="pr-3">{c.receiving_margin_fraction == null ? '—' : `${c.receiving_margin_fraction >= 0 ? '+' : ''}${(100 * c.receiving_margin_fraction).toFixed(0)} %`}</td>
        <td><Pill tone={c.status === 'short' ? 'critical' : c.status === 'sufficient' ? 'success' : 'muted'}>{c.status === 'short' ? 'Short' : c.status === 'sufficient' ? 'Sufficient' : 'Unknown'}</Pill></td>
      </tr>)}</tbody></table></div>}

    {!!output.what_changes?.length && <div className="text-xs"><p className="font-medium">What changes at the receiving site</p>
      <ul className="mt-1 space-y-0.5">{output.what_changes.map(c => <li key={c.input}>{INPUT(c.input)}: {num(c.sending)} → {num(c.receiving)}
        {c.relative_change != null && <span className="text-text-tertiary"> ({c.relative_change >= 0 ? '+' : ''}{(100 * c.relative_change).toFixed(0)} %)</span>}</li>)}</ul></div>}

    <div className="overflow-auto"><table className="w-full text-left text-xs">
      <caption className="mb-2 text-left font-medium">Acceptance criteria</caption>
      <thead><tr className="text-text-secondary"><th className="py-1 pr-3">Criterion</th><th className="pr-3">Receiving site</th><th>Verdict and what it rests on</th></tr></thead>
      <tbody>{output.checks.map(c => { const s = STATUS[c.status] ?? { label: c.status, tone: 'neutral' as Tone, basis: '' };
        const target = c.limit != null ? `${c.operator === '<=' ? '≤' : '≥'} ${num(c.limit, c.unit)}` : c.margin != null ? `not worse than sending by ${num(c.margin, c.unit)}` : '';
        return <tr key={c.metric + c.status} className="border-t border-border-hairline align-top">
          <td className="py-2 pr-3">{METRIC[c.metric] ?? c.metric.replaceAll('_', ' ')} {target}</td>
          <td className="pr-3">{c.receiver_range ? `${num(c.receiver_range[0], c.unit)} – ${num(c.receiver_range[1], c.unit)}` : num(c.receiver_estimate, c.unit)}</td>
          <td><Pill tone={s.tone}>{s.label}</Pill> <span className="text-text-secondary">{s.basis}</span>{c.reason && <p className="mt-1 text-text-tertiary">{c.reason}</p>}</td></tr>; })}</tbody></table></div>

    {!!output.tolerances?.length && <div className="text-xs"><p className="font-medium">Stated tolerances (not yet measured)</p>
      <ul className="mt-1 space-y-0.5">{output.tolerances.map(t => <li key={t.path}>{INPUT(t.path)}: {num(t.low)} – {num(t.high, t.unit)} · {t.basis.replaceAll('_', ' ')} · {t.source}</li>)}</ul></div>}
    <p className="text-xs text-text-tertiary">{output.equipment_capability?.scope}</p>
  </div>;
}
