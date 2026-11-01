'use client';

import { useEffect, useState } from 'react';
import { Card, Pill } from '@/components/ui';

type Metric = { value: number | null } | null;
type Family = {
  attempts: number; completed: number;
  first_execution_field_identity: { precision: number; recall: number; f1: number; tp: number; fp: number; fn: number };
  completed_service_latency_seconds: { p90: number; p99: number };
};
type Attempt = { case_id: string; status: string; failure_category: string | null; critical_evidence_recall: Metric; admitted_requests: number | null; request_limit: number | null };
type Study = {
  ingestion: { families: Record<string, Family>; process_peak_rss_bytes: number; integrity_pass: boolean };
  baseline: Attempt[]; agent_attempts: Attempt[]; regression_checks: { tests: number };
  limits: string[]; source_sha256: string;
};
const BASE = '/case-study-results/workflows/';
const percent = (value: number | null | undefined) => value == null ? 'Unscored' : `${(value * 100).toFixed(2)}%`;
const failureNames: Record<string, string> = {
  credential_not_loaded: 'Credential was not loaded',
  benchmark_gate_token_field_incompatibility: 'Benchmark gate rejected the SDK token-limit field',
  benchmark_request_cap: 'Stopped at the benchmark request cap',
  benchmark_admission_cap: 'Stopped at the benchmark spending gate',
  benchmark_reservation_concurrency: 'Benchmark gate rejected temporary concurrent reservations; queuing was subsequently corrected',
};

export function WorkflowStudy() {
  const [data, setData] = useState<Study | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(BASE + 'summary.json', { signal: controller.signal })
      .then(response => { if (!response.ok) throw Error('Unavailable'); return response.json(); })
      .then(setData).catch(reason => { if (reason.name !== 'AbortError') setError(true); });
    return () => controller.abort();
  }, []);
  if (!data) return <Card className="p-6"><p role="status">{error ? 'Benchmark results could not be loaded.' : 'Loading recorded benchmark results…'}</p>{error && <a className="mt-3 inline-block text-brand-teal underline" href={BASE + 'report.md'}>Open the execution report</a>}</Card>;
  const families = Object.entries(data.ingestion.families);
  return <article className="space-y-7">
    <div><Pill tone="neutral">Partial workflow evaluation · October 31, 2026</Pill><h2 className="mt-4 text-3xl font-semibold tracking-tight">Manufacturing workflow benchmarks</h2><p className="mt-3 max-w-3xl text-sm leading-6 text-text-secondary">Measured ingestion performance and investigation attempts, with failures retained. Physical simulations are separate. The larger investigation, deviation, scheduling and ingestion study remains incomplete.</p></div>
    <div className="grid gap-4 sm:grid-cols-3">{[
      [String(families.reduce((sum, [, value]) => sum + value.attempts, 0)), 'Ingestion service executions', '100 repeats of each of three packages'],
      [String(data.baseline.length), 'Deterministic investigation cases', 'A fixed baseline, separate from GLM'],
      [String(data.regression_checks.tests), 'Workflow regression checks', 'Software checks, separate from agent accuracy'],
    ].map(([value, title, detail]) => <Card key={title} className="p-5"><p className="text-3xl font-semibold tabular-nums">{value}</p><h3 className="mt-2 text-sm font-semibold">{title}</h3><p className="mt-1 text-xs leading-5 text-text-secondary">{detail}</p></Card>)}</div>
    <section className="space-y-3"><h3 className="text-xl font-semibold">Local ingestion: accuracy and latency</h3><p className="text-sm leading-6 text-text-secondary">These timings cover parsing, validation and local persistence. They exclude calibration, network requests and model inference. Repeated packages measure timing variability; they are not independent manufacturing incidents.</p><div className="overflow-x-auto rounded-xl border border-border-hairline"><table className="w-full min-w-[640px] text-left text-xs"><caption className="sr-only">Local ingestion service results across three package layouts</caption><thead className="bg-surface-secondary"><tr>{['Layout', 'Completed / attempted', 'Precision', 'Recall', 'F1', 'p90 (s)', 'p99 (s)'].map(label => <th key={label} scope="col" className="px-4 py-3">{label}</th>)}</tr></thead><tbody>{families.map(([name, family]) => <tr key={name} className="border-t border-border-hairline"><th scope="row" className="px-4 py-4 capitalize">{name}</th><td className="px-4 py-4">{family.completed}/{family.attempts}</td>{[family.first_execution_field_identity.precision, family.first_execution_field_identity.recall, family.first_execution_field_identity.f1].map((value, index) => <td key={index} className="px-4 py-4 tabular-nums">{percent(value)}</td>)}<td className="px-4 py-4 tabular-nums">{family.completed_service_latency_seconds.p90.toFixed(3)}</td><td className="px-4 py-4 tabular-nums">{family.completed_service_latency_seconds.p99.toFixed(3)}</td></tr>)}</tbody></table></div><p className="text-xs leading-5 text-text-secondary">Changed layouts produced seven extra fields despite recovering every expected present field. No silent omissions or incorrect auto-acceptances were observed. New and changed layouts still require substantial review. Peak campaign process memory: {(data.ingestion.process_peak_rss_bytes / 1048576).toFixed(1)} MiB.</p></section>
    <section className="space-y-3"><h3 className="text-xl font-semibold">Actual GLM 5.3 investigation attempts</h3><p className="text-sm leading-6 text-text-secondary">The isolated manufacturing investigation runtime used the existing Modal endpoint. Setup failures, spending-gate interruptions and subsequent attempts all remain in the denominator. This does not establish performance across the full deployed application.</p><div className="space-y-2">{data.agent_attempts.map((attempt, index) => <div key={index} className="rounded-xl border border-border-hairline p-4 text-sm"><p className="font-semibold">Attempt {index + 1} · {attempt.case_id} · {attempt.status}</p><p className="mt-1 text-xs text-text-secondary">{attempt.failure_category ? failureNames[attempt.failure_category] || attempt.failure_category : `Critical evidence recall: ${percent(attempt.critical_evidence_recall?.value)}. Independent qualification remains pending.`}</p>{attempt.admitted_requests != null && <p className="mt-2 text-xs tabular-nums text-text-secondary">{attempt.admitted_requests} forwarded model requests · limit {attempt.request_limit}</p>}</div>)}</div></section>
    <section className="rounded-xl border border-border-hairline p-5"><h3 className="font-semibold">Coverage still needed</h3><p className="mt-2 text-sm leading-6 text-text-secondary">Deviation detection has no scored agent suite yet. Manufacturing resource scheduling has no executable optimizer admitted to this benchmark. Evidence precision and recall remain unscored where defensible relevance labels are missing. None of these gaps count as a passing result.</p></section>
    <details className="rounded-xl border border-border-hairline p-5"><summary className="cursor-pointer text-sm font-semibold">Evidence and limitations</summary><ul className="mt-4 list-disc space-y-2 pl-5 text-xs leading-6 text-text-secondary">{data.limits.map(limit => <li key={limit}>{limit}</li>)}</ul><p className="mt-4 break-all font-mono text-[10px] text-text-tertiary">Source summary SHA-256: {data.source_sha256}</p></details>
    <div className="flex flex-wrap gap-5 text-sm text-brand-teal"><a href={BASE + 'report.md'} download className="underline">Download execution report</a><a href={BASE + 'summary.json'} download className="underline">Download results</a><a href={BASE + 'checksums.json'} download className="underline">Verify file checksums</a></div>
  </article>;
}
