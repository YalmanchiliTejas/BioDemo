'use client';

import { useEffect, useState } from 'react';
import { Button, Card, CardHeader } from '@/components/ui';
import { useCompanion } from '@/lib/companion-context';

type Citation = { evidence_id: string; text: string; source_url?: string; available_at?: string; source: { path: string; page?: number; row?: number; sheet?: string; span?: string; cell?: string } };
type Run = { id: string; case: string; mode: string; status: string; corpus_files: number; corpus_version: string; corpus_sha256: string; error?: string; failure_reason?: string; wall_seconds: number; metrics?: Record<string, unknown> };
type Detail = { objective: string; analysis: Record<string, unknown>; citations: Citation[]; trace: Array<Record<string, unknown>>; ingestion: Record<string, unknown>; sources: Array<{ path: string; sha256: string; available_at: string; source_url?: string }>; cutoff: string; source_package_sha256: string };
type Report = { disclosure: string; runs: Run[]; details: Record<string, Detail>; indpensim: Record<string, unknown> | null; simulator: Record<string, unknown> | null };
const format = (v: unknown) => typeof v === 'number' ? (v <= 1 && v >= 0 ? `${(v * 100).toFixed(1)}%` : v.toFixed(2)) : v == null ? 'not evaluated' : String(v);

export function LegacyCaseStudy({ caseId }: { caseId: 'sanofi' | 'indpensim' }) {
  const companion = useCompanion();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState(''); const [selected, setSelected] = useState('');
  const tab = caseId; const [filter, setFilter] = useState('');
  const [variable, setVariable] = useState('temperature(K)');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/case-study-results/report.json', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('No exported benchmark run is available. Generate and export measured results using docs/case_studies/README.md.');
      const data = await response.json() as Report; setReport(data);
      setSelected(data.runs.find(r => data.details[r.id] && r.mode === 'linked_rules')?.id ?? '');
    }).catch(e => { if (e.name !== 'AbortError') setError(String(e.message)); });
    return () => controller.abort();
  }, []);
  const detail = report?.details[selected];
  const comparisons = report?.indpensim?.batch_comparisons as Record<string, { columns: string[]; rows: Array<Array<string | number>> }> | undefined;
  return <div className="max-w-[1280px] mx-auto space-y-4">
    {error && <p role="alert" className="p-4 border rounded-card text-status-critical">{error}</p>}
    {!report && !error && <p role="status">Loading measured results…</p>}
    {report && tab === 'sanofi' && <>
      <Card className="p-4 text-sm space-y-2"><p>{report.disclosure}</p><p>The FDA’s amended January 15, 2025 letter reports approximately 20% rejected attempted bioreactor runs during January 2022–July 2024, due to contamination or other quality failures. The operational records here are fictional and establish no real Sanofi root cause.</p><a className="text-brand-teal underline" href="https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/sanofi-690604-01152025" target="_blank" rel="noreferrer">Read FDA letter · finding 1, 1A–1B and 2B</a></Card>
      <Card><CardHeader title="Benchmark results" subtitle="File discovery does not establish that the critical evidence was read. Null scores remain unmeasured." /><div className="overflow-auto"><table className="w-full text-sm text-left"><thead><tr>{['Case / method', 'Files', 'Status', 'Critical spans', 'File precision', 'Affected recall', 'Wall time'].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead><tbody>{report.runs.map(run => <tr key={run.id} className="border-t"><td className="p-3"><button className="text-brand-teal underline text-left" onClick={() => setSelected(run.id)}>{run.case} / {run.mode}</button></td><td title={run.corpus_sha256}>{run.corpus_files}<br /><small>{run.corpus_version}</small></td><td>{run.status}</td><td>{format(run.metrics?.critical_span_recall)}</td><td>{format(run.metrics?.retrieved_file_precision)}</td><td>{format(run.metrics?.affected_run_recall)}</td><td>{run.wall_seconds.toFixed(1)} s</td></tr>)}</tbody></table></div></Card>
      {report.runs.find(r => r.id === selected)?.error && <p role="alert" className="p-4 border rounded-card break-words">{report.runs.find(r => r.id === selected)?.failure_reason ?? report.runs.find(r => r.id === selected)?.error}</p>}
      {selected && !detail && report.runs.find(r => r.id === selected)?.status === 'completed' && <p role="status" className="p-4 border rounded-card text-sm">This run’s source corpus was not included in this export. Export its matching corpus to enable source drill-down.</p>}
      {detail && <>
        <Card className="p-4 text-sm"><p className="font-medium">{detail.objective}</p><p>Historical availability cutoff: {detail.cutoff}. Only eligible source bytes were staged.</p><details className="mt-3"><summary className="cursor-pointer">Ingestion coverage and failures</summary><pre className="overflow-auto text-xs mt-2">{JSON.stringify(detail.ingestion, null, 2)}</pre></details><details className="mt-3"><summary className="cursor-pointer">Findings, scope, hypotheses and limitations</summary><pre className="overflow-auto whitespace-pre-wrap text-xs mt-2">{JSON.stringify(detail.analysis, null, 2)}</pre></details></Card>
        <Card><CardHeader title="Evidence and source references" subtitle="Open original source bytes; page, row and paragraph references remain attached." /><div className="p-4"><label className="text-sm">Filter evidence <input className="border rounded-control p-2 w-full my-2" value={filter} onChange={e => setFilter(e.target.value)} /></label><div className="max-h-[480px] overflow-auto space-y-3">{detail.citations.filter(c => `${c.text} ${c.source.path}`.toLowerCase().includes(filter.toLowerCase())).map(c => <article className="border-t pt-3 text-sm" key={c.evidence_id}><p>{c.text}</p><a className="text-brand-teal underline break-all" href={c.source_url} target="_blank" rel="noreferrer">{c.source.path}</a><p className="text-xs text-text-tertiary">{c.source.sheet} {c.source.cell} {c.source.row ? `row ${c.source.row}` : ''} {c.source.page ? `page ${c.source.page}` : ''} {c.source.span} · {c.evidence_id}</p></article>)}</div></div></Card>
        <div className="grid md:grid-cols-2 gap-4"><Card className="p-4"><details><summary className="cursor-pointer text-sm">Source explorer · {detail.sources.length} available files</summary><ul className="max-h-80 overflow-auto text-xs space-y-2 mt-3">{detail.sources.map(s => <li key={s.path}><a className="text-brand-teal underline" href={s.source_url} target="_blank" rel="noreferrer">{s.path}</a><br />Available {s.available_at}<br /><span className="break-all">SHA-256 {s.sha256}</span></li>)}</ul></details></Card><Card className="p-4"><details><summary className="cursor-pointer text-sm">Discovery and inspection trace · {detail.trace.length} events</summary><ol className="max-h-80 overflow-auto text-xs space-y-2 mt-3">{detail.trace.map((t, i) => <li key={i}><pre className="whitespace-pre-wrap">{JSON.stringify(t, null, 2)}</pre></li>)}</ol></details></Card></div>
        <Button onClick={() => companion.show({ kind:'text', label:'Case evidence · '+selected, page_path:'/case-studies', captured_at:new Date().toISOString(), content:JSON.stringify({ objective:detail.objective, cutoff:detail.cutoff, source_package_sha256:detail.source_package_sha256, citations:detail.citations }) })}>Discuss selected evidence with the companion</Button>
      </>}
    </>}
    {report && tab === 'indpensim' && <>
      <Card className="p-4 text-sm space-y-2"><p>Stephen Goldrick’s IndPenSim v2 dataset contains simulation-derived historical batches under different control strategies. Group differences do not establish causal intervention effects.</p><a className="text-brand-teal underline" href="https://data.mendeley.com/datasets/pdnjz7zz5x/2">Dataset, source version and CC BY 4.0 license</a></Card>
      {comparisons && <Card><CardHeader title="Compare historical batches" subtitle="Full-trajectory descriptive statistics in original variable units. Control groups are not matched experiments." /><div className="p-4"><label className="text-sm">Process variable <select className="border rounded-control p-2 ml-2" value={variable} onChange={e => setVariable(e.target.value)}>{Object.keys(comparisons).map(key => <option key={key}>{key}</option>)}</select></label><div className="max-h-80 overflow-auto mt-3"><table className="w-full text-sm text-left"><thead><tr>{comparisons[variable]?.columns.map(column => <th key={column} className="p-2">{column}</th>)}</tr></thead><tbody>{comparisons[variable]?.rows.map(row => <tr key={String(row[0])} className="border-t">{row.map((value, i) => <td className="p-2" key={i}>{typeof value === 'number' ? value.toPrecision(6) : value}</td>)}</tr>)}</tbody></table></div></div></Card>}
      <Card><CardHeader title="Historical ingestion and fault screen" subtitle="Deterministic descriptive measurements; agent investigation and onset accuracy remain unmeasured." /><pre className="p-4 text-xs overflow-auto whitespace-pre-wrap">{report.indpensim ? JSON.stringify(report.indpensim, null, 2) : 'Historical benchmark has not been exported.'}</pre></Card>
      <Card><CardHeader title="Simulator feasibility and matched experiments" subtitle="A numerical failure blocks optimization claims. Full episode artifacts remain in the evaluation report." /><pre className="p-4 text-xs overflow-auto whitespace-pre-wrap">{report.simulator ? JSON.stringify(report.simulator, null, 2) : 'Simulator gate has not been exported.'}</pre></Card>
    </>}
  </div>;
}
