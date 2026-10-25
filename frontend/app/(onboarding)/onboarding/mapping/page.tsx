'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, ArrowLeft, ArrowRight, Check, ChevronDown, ChevronUp, Copy, FileSpreadsheet, FileText, Loader2, Table2 } from 'lucide-react';
import { Button, Card, CardHeader, ClaimTag, EvidenceChip, LinkButton, Pill, ProgressBar, table, type Tone } from '@/components/ui';
import { StandaloneEvidence } from '@/components/screens/a/StandaloneEvidence';
import { TZ_STORAGE_KEY, writeSession } from '@/components/screens/a/onboarding';
import { cn } from '@/lib/cn';

type IntakeFile = { name: string; system: string; records: number; kind: 'table' | 'doc' };

const FILES: IntakeFile[] = [
  { name: 'Historian_UP01_Oct.csv', system: 'OSIsoft PI', records: 12480, kind: 'table' },
  { name: 'Batch_events_UP01.parquet', system: 'DeltaV eBR', records: 5310, kind: 'table' },
  { name: 'LIMS_CMP-26-10_results.xlsx', system: 'LabWare LIMS', records: 2316, kind: 'table' },
  { name: 'eBR_MES-26071.pdf', system: 'DeltaV eBR', records: 1212, kind: 'doc' },
  { name: 'eBR_MES-26072.pdf', system: 'DeltaV eBR', records: 1198, kind: 'doc' },
  { name: 'eBR_MES-26073.pdf', system: 'DeltaV eBR', records: 1064, kind: 'doc' },
  { name: 'Maximo_WO_export.csv', system: 'Maximo CMMS', records: 486, kind: 'table' },
  { name: 'QMS_deviations.xlsx', system: 'Veeva Vault QMS', records: 124, kind: 'table' },
];
const TOTAL_RECORDS = FILES.reduce((s, f) => s + f.records, 0); // 24,190

type MappingRow = {
  source: string;
  file: string;
  sample: string;
  target: string;
  method: string;
  methodTone: Tone;
  units?: string[];
  exception?: 'AMBIGUOUS_TIMEZONE';
};

const MAPPINGS: MappingRow[] = [
  { source: 'EVENT_TS_RAW', file: 'Batch_events_UP01.parquet', sample: '2026-10-19 08:26:00', target: 'ProcessEvent.timestamp', method: 'Format detected · no UTC offset', methodTone: 'warning', exception: 'AMBIGUOUS_TIMEZONE' },
  { source: 'TS_UTC', file: 'Historian_UP01_Oct.csv', sample: '2026-10-19T08:26:00Z', target: 'Measurement.timestamp', method: 'Exact header match · ISO-8601 Z', methodTone: 'success' },
  { source: 'BATCH_NO', file: 'Batch_events_UP01.parquet', sample: 'MES-26073', target: 'Batch.batchId', method: 'Exact header match', methodTone: 'success' },
  { source: 'UNIT_ID', file: 'Batch_events_UP01.parquet', sample: 'BR-UP-01', target: 'Unit.unitId', method: 'Exact header match', methodTone: 'success' },
  { source: 'PHASE', file: 'Batch_events_UP01.parquet', sample: '05', target: 'Phase.phaseId', method: 'Value dictionary match (eBR phase list)', methodTone: 'success' },
  { source: 'PM204.FLOW_PV', file: 'Historian_UP01_Oct.csv', sample: '14.48', target: 'ControlModule.PM-204.feedRate', method: 'Tag dictionary match · unit from tag metadata', methodTone: 'success', units: ['mL/min', 'L/h'] },
  { source: 'PM204.HEAD_P', file: 'Historian_UP01_Oct.csv', sample: '1.48', target: 'ControlModule.PM-204.dischargePressure', method: 'Unit inferred from value range (0.8–1.5)', methodTone: 'info', units: ['bar', 'psi', 'kPa'] },
  { source: 'TITER_RES', file: 'LIMS_CMP-26-10_results.xlsx', sample: '3.42', target: 'SampleResult.titer', method: 'Unit inferred from LIMS spec field', methodTone: 'info', units: ['g/L', 'mg/mL'] },
  { source: 'WO_NUM', file: 'Maximo_WO_export.csv', sample: 'WO-8819', target: 'MaintenanceEvent.workOrderId', method: 'Exact header match', methodTone: 'success' },
  { source: 'DEV_ID', file: 'QMS_deviations.xlsx', sample: 'Q-DEV-031', target: 'QualityEvent.deviationId', method: 'Pattern match (Q-DEV-###)', methodTone: 'success' },
];

const PREVIEW = [
  ['2026-10-19 08:17:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_START', '16.90'],
  ['2026-10-19 08:18:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.87'],
  ['2026-10-19 08:19:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.91'],
  ['2026-10-19 08:20:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.84'],
  ['2026-10-19 08:21:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.88'],
  ['2026-10-19 08:22:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.80'],
  ['2026-10-19 08:23:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.86'],
  ['2026-10-19 08:24:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '16.88'],
  ['2026-10-19 08:25:00', 'MES-26073', 'BR-UP-01', '05', 'FEED_PV', '15.12'],
  ['2026-10-19 08:26:00', 'MES-26073', 'BR-UP-01', '05', 'HEAD_P_ALM', '1.48'],
];

type Tz = 'UTC' | 'SITE';
const TZ_LABEL: Record<Tz, string> = { UTC: 'UTC', SITE: 'Site local (America/Phoenix, UTC−7)' };

export default function OnboardingMappingPage() {
  const router = useRouter();
  const [tick, setTick] = useState(0);
  const [tz, setTz] = useState<Tz>('UTC');
  const [units, setUnits] = useState<Record<string, string>>(() => Object.fromEntries(MAPPINGS.filter((m) => m.units).map((m) => [m.source, m.units![0]])));
  const [included, setIncluded] = useState<Record<string, boolean>>(() => Object.fromEntries(MAPPINGS.map((m) => [m.source, true])));
  const [preview, setPreview] = useState(false);
  const [showDupes, setShowDupes] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => (t >= 20 ? t : t + 1)), 220);
    return () => clearInterval(id);
  }, []);

  // Files finish one after another; each takes a few ticks.
  const progress = useMemo(() => FILES.map((_, i) => Math.max(0, Math.min(100, (tick - i * 1.6) * 34))), [tick]);
  const parsedRecords = Math.round(FILES.reduce((s, f, i) => s + (f.records * progress[i]) / 100, 0));
  const parsingDone = progress.every((p) => p >= 100);
  const includedCount = Object.values(included).filter(Boolean).length;

  const confirm = () => {
    writeSession(TZ_STORAGE_KEY, tz);
    router.push('/onboarding/results');
  };

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Step 2 of 3 · ONB-02</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-text-primary">Confirm how your data maps</h1>
          <p className="mt-1 text-[13px] text-text-secondary max-w-2xl">
            Columns were matched to ISA-88 batch entities automatically. Only one question needs your answer; everything else can be reviewed or changed later from Sources.
          </p>
        </div>
        <Pill tone="muted">Source files are not modified</Pill>
      </div>

      {/* The one question we cannot answer for the user */}
      <div className="mt-5 rounded-card border border-amber-300 bg-status-warning-bg p-4" role="region" aria-labelledby="tz-q">
        <div className="flex items-start gap-2.5">
          <AlertTriangle className="h-4 w-4 mt-0.5 text-status-warning shrink-0" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 id="tz-q" className="text-[13.5px] font-semibold text-amber-900">Which time zone are <code className="font-mono text-[12.5px]">EVENT_TS_RAW</code> timestamps in?</h2>
            <p className="mt-0.5 text-[12.5px] text-amber-900/90">
              Batch_events_UP01.parquet has no UTC offset. The historian file is explicitly UTC, so a wrong choice would shift eBR phase events by 7 h against telemetry. Suggested: <span className="font-semibold">UTC</span> — eBR phase 05.4 start aligns with the historian feed-start within 1 min under UTC, and is 7 h off under site local.
            </p>
            <fieldset className="mt-3">
              <legend className="sr-only">Time zone for EVENT_TS_RAW</legend>
              <div className="flex flex-wrap gap-2">
                {(['UTC', 'SITE'] as Tz[]).map((v) => (
                  <label key={v} className={cn('flex items-center gap-2 h-8 px-3 rounded-control border cursor-pointer text-[12.5px] bg-surface focus-within:ring-2 focus-within:ring-brand-teal', tz === v ? 'border-brand-teal text-text-primary font-medium' : 'border-amber-200 text-text-secondary')}>
                    <input type="radio" name="tz" value={v} checked={tz === v} onChange={() => setTz(v)} className="accent-[#0e7490]" />
                    {TZ_LABEL[v]}
                    {v === 'UTC' && <span className="text-[10.5px] text-text-tertiary font-normal">suggested</span>}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)] gap-4">
        {/* Intake queue */}
        <Card className="self-start">
          <CardHeader
            title="Intake queue"
            subtitle={`${parsedRecords.toLocaleString()} / ${TOTAL_RECORDS.toLocaleString()} records parsed`}
            actions={parsingDone ? <Pill tone="success" dot>Complete</Pill> : <Pill tone="info"><Loader2 className="h-3 w-3 animate-spin" aria-hidden />Parsing</Pill>}
          />
          <ul className="divide-y divide-border-hairline" aria-live="polite">
            {FILES.map((f, i) => {
              const Icon = f.kind === 'doc' ? FileText : FileSpreadsheet;
              const done = progress[i] >= 100;
              return (
                <li key={f.name} className="px-4 py-2.5">
                  <div className="flex items-center gap-2 text-[12px]">
                    <Icon className="h-3.5 w-3.5 text-text-tertiary shrink-0" aria-hidden />
                    <span className="font-mono truncate text-text-primary" title={f.name}>{f.name}</span>
                    {done && <Check className="ml-auto h-3.5 w-3.5 text-status-success shrink-0" aria-label="Parsed" />}
                  </div>
                  <ProgressBar className="mt-1.5" value={progress[i]} tone={done ? 'success' : 'brand'} label={`${f.name} parsing progress`} />
                  <p className="mt-1 flex justify-between text-[10.5px] text-text-tertiary tabular-nums">
                    <span>{f.system}{f.kind === 'doc' ? ' · text + tables extracted' : ''}</span>
                    <span>{f.records.toLocaleString()} rec</span>
                  </p>
                </li>
              );
            })}
          </ul>
          <div className="px-4 py-3 border-t border-border-hairline">
            <div className="flex items-start gap-2 text-[12px]">
              <Copy className="h-3.5 w-3.5 mt-0.5 text-text-tertiary shrink-0" aria-hidden />
              <div className="min-w-0">
                <p className="text-text-primary"><span className="font-semibold tabular-nums">37</span> duplicate records detected · kept once</p>
                <button type="button" onClick={() => setShowDupes((s) => !s)} className="text-[11.5px] text-brand-teal hover:underline" aria-expanded={showDupes}>
                  {showDupes ? 'Hide details' : 'Show details'}
                </button>
                {showDupes && (
                  <p className="mt-1 text-[11.5px] text-text-secondary">
                    Rows in Historian_UP01_Oct.csv with identical timestamp, tag and value (overlapping export windows on 2026-10-12). Rule: exact match on (TS_UTC, TAG, VALUE). Originals remain in the source file; nothing was deleted.
                  </p>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Mapping table */}
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              title="Column → ISA-88 entity mapping"
              subtitle={`${MAPPINGS.length} key columns shown of 64 detected · ${includedCount} included`}
              actions={
                <Button size="sm" variant="ghost" onClick={() => setPreview((p) => !p)} aria-expanded={preview}>
                  <Table2 className="h-3.5 w-3.5" aria-hidden /> Data preview {preview ? <ChevronUp className="h-3 w-3" aria-hidden /> : <ChevronDown className="h-3 w-3" aria-hidden />}
                </Button>
              }
            />
            <div className={table.wrap}>
              <table className={table.root}>
                <thead>
                  <tr>
                    <th className={table.th}><span className="sr-only">Include</span></th>
                    <th className={table.th}>Source column</th>
                    <th className={table.th}>Sample</th>
                    <th className={table.th}>Canonical property</th>
                    <th className={table.th}>Unit</th>
                    <th className={table.th}>How it was matched</th>
                  </tr>
                </thead>
                <tbody>
                  {MAPPINGS.map((m) => (
                    <tr key={m.source} className={cn(table.tr, m.exception && 'bg-status-warning-bg/60', !included[m.source] && 'opacity-50')}>
                      <td className={cn(table.td, 'w-8')}>
                        <input
                          type="checkbox"
                          checked={included[m.source]}
                          onChange={(e) => setIncluded((s) => ({ ...s, [m.source]: e.target.checked }))}
                          aria-label={`Include ${m.source}`}
                          className="accent-[#0e7490]"
                        />
                      </td>
                      <td className={table.td}>
                        <code className="font-mono text-[12px] text-text-primary">{m.source}</code>
                        <p className="text-[10.5px] text-text-tertiary truncate max-w-[180px]" title={m.file}>{m.file}</p>
                      </td>
                      <td className={cn(table.td, 'font-mono text-[11.5px] text-text-secondary whitespace-nowrap')}>{m.sample}</td>
                      <td className={cn(table.td, 'font-mono text-[11.5px]')}>{m.target}</td>
                      <td className={table.td}>
                        {m.units ? (
                          <select
                            value={units[m.source]}
                            onChange={(e) => setUnits((s) => ({ ...s, [m.source]: e.target.value }))}
                            aria-label={`Unit for ${m.source}`}
                            className="h-7 px-1.5 rounded-control border border-border-strong bg-surface text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal"
                          >
                            {m.units.map((u) => <option key={u}>{u}</option>)}
                          </select>
                        ) : m.exception ? (
                          <span className="text-[11.5px] font-medium text-amber-700">{tz === 'UTC' ? 'UTC' : 'UTC−7'}</span>
                        ) : (
                          <span className="text-text-muted text-xs">—</span>
                        )}
                      </td>
                      <td className={table.td}>
                        {m.exception ? (
                          <Pill tone="warning">{tz === 'UTC' ? 'Ambiguous TZ · UTC selected' : 'Ambiguous TZ · site local selected'}</Pill>
                        ) : (
                          <Pill tone={m.methodTone}>{m.method}</Pill>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="px-4 py-2.5 text-[11px] text-text-tertiary border-t border-border-hairline">
              Match method describes how a mapping was found, not a probability that it is correct. Unit changes affect display and calculations only; source values are stored as received.
            </p>
          </Card>

          {preview && (
            <Card>
              <CardHeader title="Data preview · first 10 mapped rows" subtitle="Batch_events_UP01.parquet joined to historian feed values" actions={<ClaimTag kind="observation" />} />
              <div className={table.wrap}>
                <table className={table.root}>
                  <thead>
                    <tr>
                      {[`ProcessEvent.timestamp (${tz === 'UTC' ? 'UTC' : 'UTC−7'})`, 'Batch.batchId', 'Unit.unitId', 'Phase.phaseId', 'Event', `Value (${units['PM204.FLOW_PV']})`].map((h) => <th key={h} className={table.th}>{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {PREVIEW.map((r, i) => (
                      <tr key={i} className={table.tr}>
                        {r.map((c, j) => {
                          let v = c;
                          if (j === 5 && r[4] !== 'HEAD_P_ALM' && units['PM204.FLOW_PV'] === 'L/h') v = ((parseFloat(c) * 60) / 1000).toFixed(3);
                          if (j === 5 && r[4] === 'HEAD_P_ALM') v = `${c} bar`;
                          return <td key={j} className={cn(table.td, 'py-1.5 font-mono text-[11.5px]', j === 5 && 'text-right')}>{v}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-4 py-2.5 border-t border-border-hairline flex flex-wrap items-center gap-2 text-[11px] text-text-tertiary">
                Corresponding historian rows: <EvidenceChip id="historian-up01" />
              </div>
            </Card>
          )}

          <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-1">
            <LinkButton href="/onboarding/start" variant="ghost"><ArrowLeft className="h-3.5 w-3.5" aria-hidden />Cancel / Back</LinkButton>
            <div className="flex flex-col sm:items-end gap-1">
              <Button variant="primary" size="lg" onClick={confirm} disabled={!parsingDone}>
                {parsingDone ? `Confirm ${tz === 'UTC' ? 'UTC' : 'site local'} & Accept All Mappings` : 'Waiting for parsing to finish…'}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
              <p className="text-[11px] text-text-tertiary">Mappings are reused for future uploads from the same systems.</p>
            </div>
          </div>
        </div>
      </div>
      <StandaloneEvidence />
    </div>
  );
}
