'use client';

import { useState } from 'react';
import { ArrowLeft, CheckCircle2, CircleDashed, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react';
import { Callout, Card, CardBody, CardHeader, ClaimTag, DemoBoundary, EvidenceChip, LinkButton, PageHeader, Pill, SectionLabel, table, type Tone } from '@/components/ui';
import { ProposalFields } from '@/components/screens/b/ProposalFields';
import { cn } from '@/lib/cn';

type ScenarioKey = 'base' | 'A' | 'B';
type Scenario = {
  key: ScenarioKey;
  name: string;
  mode: string;
  delta: string;
  range: string;
  status: { label: string; tone: Tone };
  note: string;
  risk: { l: 0 | 1 | 2; s: 0 | 1 | 2 };
};

const SCENARIOS: Scenario[] = [
  { key: 'base', name: 'Baseline', mode: 'Open-loop RPM (current)', delta: '±0.0 pts', range: 'Recurrence expected if tubing wear repeats', status: { label: 'Reference', tone: 'neutral' }, note: 'Pump runs at fixed RPM; delivered volume falls as tubing wears or occlusion changes, and nothing corrects it.', risk: { l: 2, s: 1 } },
  { key: 'A', name: 'Candidate A', mode: 'Closed-loop mass-balance feed cascade', delta: '+5.1 pts', range: 'Range +3.2 to +6.8 pts', status: { label: 'Proposed for review', tone: 'brand' }, note: 'Feed-tote load cell trims pump RPM every 2 s so delivered mass tracks setpoint; head-pressure interlock at 1.20 bar.', risk: { l: 0, s: 1 } },
  { key: 'B', name: 'Candidate B', mode: 'High-shear RPM compensation', delta: 'n/a', range: 'Not estimated — disqualified on limits before modelling', status: { label: 'Disqualified', tone: 'critical' }, note: 'Raises pump speed to compensate for slip. Exceeds the OEM ≤200 RPM tubing limit and projects head pressure above the 1.20 bar ceiling.', risk: { l: 1, s: 2 } },
];

const PARAMS: Array<{ p: string; unit: string; base: string; a: string; b: string; flagB?: boolean; flagA?: boolean }> = [
  { p: 'Feed control mode', unit: '', base: 'Open-loop RPM', a: 'Mass-balance cascade', b: 'Open-loop RPM + offset', flagA: true },
  { p: 'Feed setpoint', unit: 'mL/min', base: '16.90', a: '16.90', b: '16.90' },
  { p: 'Pump speed', unit: 'RPM', base: '184.2 fixed', a: '172–196 (controller)', b: '212 fixed', flagB: true, flagA: true },
  { p: 'Gravimetric trim interval', unit: 's', base: '—', a: '2', b: '—', flagA: true },
  { p: 'Head-pressure action at 1.20 bar', unit: '', base: 'Alarm only', a: 'Alarm + RPM hold', b: 'Alarm only', flagA: true },
  { p: 'Projected peak head pressure', unit: 'bar', base: '1.48 (observed)', a: '≤ 1.15', b: '1.35', flagB: true },
  { p: 'Tubing changeout interval', unit: 'h', base: '500', a: '400', b: '500 (OEM life shortened)', flagA: true, flagB: true },
];

type Check = { text: string; state: 'met' | 'unmet' | 'unverified'; cite?: string };
const CONSTRAINTS: Check[] = [
  { text: 'Pump speed within OEM tubing limit (≤ 200 RPM)', state: 'met', cite: 'oem-masterflex' },
  { text: 'Head pressure stays below the 1.20 bar ceiling', state: 'met' },
  { text: 'Feed-tote load cell LC-204 installed on BR-UP-01 skid', state: 'met' },
  { text: 'LC-204 calibration current', state: 'unverified' },
  { text: 'DeltaV cascade block available in the current control-system version', state: 'met' },
  { text: 'Change control raised for recipe and control strategy', state: 'unmet' },
  { text: 'Durham recipient loop can be mapped (TT-006 item 2.7)', state: 'unmet', cite: 'b-tt006-gate2' },
  { text: 'Operator training on new alarm response', state: 'unmet' },
];

const ASSUMPTIONS = [
  'Feed-loss-to-yield relationship from AN-104 (3 batches) holds for future batches; small sample, wide uncertainty.',
  'Hypothesis A (tubing slip) is the main driver of the feed shortfall. If tests TP-01/TP-02 contradict it, this estimate no longer applies.',
  'Controller holds delivered mass within ±2% of setpoint; tuning not yet tested on this skid.',
  'No change to media, cell line, temperature profile or harvest timing.',
  'Range reflects bootstrap resampling of the 3-batch fit (5th–95th percentile); it is not a probability that the outcome will fall inside it.',
];

const LIK = ['Low', 'Medium', 'High'];
const SEV = ['Minor', 'Moderate', 'Major'];

function RiskMatrix({ active }: { active: ScenarioKey }) {
  const cell = 64, ox = 70, oy = 10;
  const color = (l: number, s: number) => {
    const score = l + s;
    return score >= 3 ? '#fee2e2' : score === 2 ? '#fef3c7' : '#ecfdf5';
  };
  const offsets: Record<ScenarioKey, number> = { base: -14, A: 0, B: 14 };
  return (
    <svg viewBox={`0 0 ${ox + cell * 3 + 10} ${oy + cell * 3 + 44}`} className="w-full max-w-[300px]" role="img" aria-label="Risk matrix of likelihood by severity for baseline, candidate A and candidate B">
      {[0, 1, 2].map((l) =>
        [0, 1, 2].map((s) => (
          <rect key={`${l}${s}`} x={ox + s * cell} y={oy + (2 - l) * cell} width={cell} height={cell} fill={color(l, s)} stroke="#ffffff" strokeWidth="2" />
        )),
      )}
      {LIK.map((t, l) => <text key={t} x={ox - 6} y={oy + (2 - l) * cell + cell / 2 + 3} fontSize="10" textAnchor="end" fill="#64748b">{t}</text>)}
      {SEV.map((t, s) => <text key={t} x={ox + s * cell + cell / 2} y={oy + cell * 3 + 14} fontSize="10" textAnchor="middle" fill="#64748b">{t}</text>)}
      <text x={ox + cell * 1.5} y={oy + cell * 3 + 32} fontSize="10" textAnchor="middle" fill="#94a3b8" fontWeight="600">SEVERITY</text>
      <text x={12} y={oy + cell * 1.5} fontSize="10" textAnchor="middle" fill="#94a3b8" fontWeight="600" transform={`rotate(-90 12 ${oy + cell * 1.5})`}>LIKELIHOOD</text>
      {SCENARIOS.map((sc) => {
        const cx = ox + sc.risk.s * cell + cell / 2 + offsets[sc.key];
        const cy = oy + (2 - sc.risk.l) * cell + cell / 2;
        const isActive = sc.key === active;
        const fill = sc.key === 'A' ? '#0e7490' : sc.key === 'B' ? '#dc2626' : '#64748b';
        return (
          <g key={sc.key}>
            <circle cx={cx} cy={cy} r={isActive ? 12 : 10} fill={fill} stroke={isActive ? '#0f172a' : '#ffffff'} strokeWidth="2" />
            <text x={cx} y={cy + 3.5} fontSize="10" fontWeight="700" textAnchor="middle" fill="#ffffff">{sc.key === 'base' ? '0' : sc.key}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function OptimizationPage() {
  const [active, setActive] = useState<ScenarioKey>('A');

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="OPT-01"
        crumbs={[{ label: 'Improve' }, { label: 'Optimization' }, { label: 'OPT-104' }]}
        title="Feed control scenarios · BR-UP-01"
        objectId="OPT-104"
        status={<><Pill tone="warning" dot>AWAITING_TECHNICAL_REVIEW</Pill><Pill tone="brand" title="Scenario outputs are model estimates for discussion. Nothing is applied to DeltaV, the recipe or equipment.">Scenario Estimate (Illustrative — Non-Autonomous)</Pill></>}
        description="Three ways to respond to late-phase feed attenuation, compared on expected yield effect, risk and practical constraints. Predicted recovery for Candidate A: +5.1 pts normalized yield (range +3.2 to +6.8)."
        meta={<><span>From investigation INV-104 · hypothesis A</span><span>Model: AN-104 feed-loss regression v1 (3 batches)</span><DemoBoundary compact /></>}
        actions={
          <>
            <LinkButton href="/investigations/INV-104"><ArrowLeft className="h-3.5 w-3.5" /> Return to causal case INV-104</LinkButton>
            <LinkButton href="/reviews/REV-01" variant="primary"><ShieldCheck className="h-3.5 w-3.5" /> Submit for technical & QA review</LinkButton>
          </>
        }
      />

      <Callout tone="warning" className="mb-4" title="These are illustrative estimates, not predictions you can bank on">
        Estimates rest on three batches and on hypothesis A, which is supported but not yet tested. Submitting sends the proposal for human review; it does not change the recipe, DeltaV configuration or equipment.
      </Callout>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4" role="radiogroup" aria-label="Scenarios">
        {SCENARIOS.map((s) => {
          const on = active === s.key;
          const dq = s.key === 'B';
          return (
            <button
              key={s.key}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setActive(s.key)}
              className={cn(
                'text-left rounded-card border bg-surface p-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal',
                on ? 'border-brand-teal ring-1 ring-brand-teal/40' : 'border-border-hairline hover:bg-surface-secondary/60',
                dq && 'bg-surface-secondary/40',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-mono text-text-tertiary">{s.name}</span>
                <Pill tone={s.status.tone}>{s.status.label}</Pill>
              </div>
              <p className={cn('mt-1 text-[14px] font-semibold', dq ? 'text-text-secondary line-through decoration-red-400' : 'text-text-primary')}>{s.mode}</p>
              <p className="mt-2 tabular-nums">
                <span className={cn('text-xl font-semibold', s.key === 'A' ? 'text-brand-teal' : 'text-text-secondary')}>{s.delta}</span>
                <span className="ml-1 text-[11px] text-text-tertiary">normalized yield</span>
              </p>
              <p className="text-[11.5px] text-text-tertiary">{s.range}</p>
              <p className="mt-2 text-[12px] text-text-secondary leading-relaxed">{s.note}</p>
              {dq && (
                <p className="mt-2 flex items-start gap-1.5 text-[11.5px] text-red-700"><ShieldAlert className="h-3.5 w-3.5 mt-0.5 shrink-0" />Disqualified: exceeds shear/tubing limits (212 RPM &gt; 200 RPM OEM; projected 1.35 bar &gt; 1.20 bar).</p>
              )}
              <div className="mt-2"><ClaimTag kind={s.key === 'A' ? 'recommendation' : s.key === 'B' ? 'contradicted' : 'observation'} /></div>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <Card className="xl:col-span-2">
          <CardHeader title="Parameter deltas" subtitle="What each scenario changes relative to the current recipe" actions={<EvidenceChip id="b-ebr-recipe-v4" label="Recipe V4" />} />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead>
                <tr>
                  <th className={table.th}>Parameter</th>
                  <th className={table.th}>Baseline</th>
                  <th className={cn(table.th, active === 'A' && 'text-brand-teal')}>Candidate A</th>
                  <th className={cn(table.th, active === 'B' && 'text-status-critical')}>Candidate B</th>
                </tr>
              </thead>
              <tbody>
                {PARAMS.map((r) => (
                  <tr key={r.p} className={table.tr}>
                    <td className={cn(table.td, 'text-[12.5px]')}>{r.p} {r.unit && <span className="text-[11px] text-text-tertiary">({r.unit})</span>}</td>
                    <td className={cn(table.td, 'text-[12.5px] text-text-secondary')}>{r.base}</td>
                    <td className={cn(table.td, 'text-[12.5px]', r.flagA && 'font-medium text-brand-teal-dark bg-brand-teal-light/40')}>{r.a}</td>
                    <td className={cn(table.td, 'text-[12.5px]', r.flagB && 'font-medium text-red-700 bg-status-critical-bg/50')}>{r.b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader title="Risk matrix" subtitle="Likelihood × severity of an adverse process outcome · team judgement" />
          <CardBody className="flex flex-col items-center">
            <RiskMatrix active={active} />
            <ul className="mt-3 w-full space-y-1 text-[11.5px] text-text-secondary">
              <li><span className="font-mono font-semibold">0</span> Baseline — feed shortfall likely to recur; moderate yield impact.</li>
              <li><span className="font-mono font-semibold text-brand-teal">A</span> Controller mis-tuning possible but bounded by RPM and pressure limits.</li>
              <li><span className="font-mono font-semibold text-status-critical">B</span> Tubing rupture or spallation risk; major impact.</li>
            </ul>
            <p className="mt-2 text-[11px] text-text-tertiary">Placements are a qualitative MSAT assessment, not a computed probability.</p>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card>
          <CardHeader title="Practical constraints · Candidate A" />
          <ul className="divide-y divide-border-hairline">
            {CONSTRAINTS.map((c) => (
              <li key={c.text} className="px-4 py-2 flex items-start gap-2 text-[12.5px]">
                {c.state === 'met' ? <CheckCircle2 className="h-4 w-4 shrink-0 text-status-success" aria-label="Met" /> : c.state === 'unmet' ? <XCircle className="h-4 w-4 shrink-0 text-status-critical" aria-label="Not met" /> : <CircleDashed className="h-4 w-4 shrink-0 text-status-warning" aria-label="Unverified" />}
                <span className="flex-1 text-text-secondary">{c.text}</span>
                {c.cite && <EvidenceChip id={c.cite} />}
              </li>
            ))}
          </ul>
          <p className="px-4 py-2.5 border-t border-border-hairline text-[11.5px] text-text-tertiary">4 met · 3 open · 1 unverified. Open items must close before implementation, not before review.</p>
        </Card>

        <Card>
          <CardHeader title="Assumptions" />
          <CardBody>
            <ol className="space-y-2 text-[12.5px] text-text-secondary list-decimal pl-4">
              {ASSUMPTIONS.map((a) => <li key={a}>{a}</li>)}
            </ol>
            <div className="mt-3 flex flex-wrap gap-2"><EvidenceChip id="b-calc-feed-pressure" /><EvidenceChip id="historian-up01" /></div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Outcome measure after implementation" />
          <CardBody className="space-y-2 text-[12.5px] text-text-secondary">
            <p><span className="font-medium text-text-primary">Primary:</span> |feed PV − SP| ≤ 3% throughout Phase 05 on the next 3 batches.</p>
            <p><span className="font-medium text-text-primary">Secondary:</span> PM-204 head pressure ≤ 1.20 bar; normalized yield index compared against the +3.2 to +6.8 pt estimate.</p>
            <p><span className="font-medium text-text-primary">Review point:</span> after MES-26076 harvest. If yield gain is below +3.2 pts, revisit hypothesis A.</p>
            <SectionLabel className="pt-1">Status tracking</SectionLabel>
            <div className="flex flex-wrap gap-1.5">
              <Pill tone="brand">Proposed</Pill><Pill tone="muted">Approved —</Pill><Pill tone="muted">Implemented —</Pill><Pill tone="muted">Effect observed —</Pill>
            </div>
          </CardBody>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title="Proposal · Candidate A" subtitle="What reviewers are being asked to evaluate" />
        <CardBody>
          <ProposalFields
            rationale="Feed shortfall tracks head pressure (R² = 0.941, correlation) and the tubing-slip mechanism is plausible. A mass-balance loop corrects delivered feed regardless of tubing condition."
            expected="+5.1 pts normalized yield (illustrative range +3.2 to +6.8) and feed delivery within ±3% of setpoint."
            constraints="Change control, LC-204 calibration check, operator training and Durham loop mapping (TT-006) remain open."
            owner="Alex Rivera (MSAT Lead) with Automation Engineering"
            approval="Technical review (MSAT + Automation) then QA review with named e-signatures in REV-01."
            wouldChange="Test TP-01 showing no slip at 0.55 N·m; controller trial showing oscillation or pressure overshoot; a new batch with full feed delivery but persistent yield loss."
          />
        </CardBody>
      </Card>
    </div>
  );
}
