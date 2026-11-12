'use client';

import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2, ZoomIn, ZoomOut } from 'lucide-react';
import { cn } from '@/lib/cn';
import { cmoFetch, type Run } from '@/lib/cmo-api';

/** Where something sits in a delivered file. Only the parts that are known are set. */
export type Location = { sourceId: string; path: string; sheet?: string | null; row?: number | null; column?: string | null; page?: number | null; region?: number[] | null };
type Excerpt = { headers: Array<string | null>; rows: Array<{ row: number; values: Array<string | null> }>; total_rows: number; row: number | null;
  sheet: string | null; sheets: string[]; sheet_assumed: boolean; columns_truncated: boolean };

const isTable = (path: string) => /\.(xlsx|xlsm|csv|tsv)$/i.test(path);
const isPdf = (path: string) => /\.pdf$/i.test(path);
/** The file a path in this delivery refers to, if it was read. */
export const sourceIdFor = (run: Run, path?: string | null) => (run.documents ?? []).find(d => d.path === path)?.source_id;
export const canShow = (path: string) => isTable(path) || isPdf(path);

function useBlob(path: string | null) {
  const [state, setState] = useState<{ url: string; headers: Headers } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!path) return;
    let url = '', alive = true;
    setState(null); setError('');
    cmoFetch(path).then(async response => {
      url = URL.createObjectURL(await response.blob());
      if (alive) setState({ url, headers: response.headers }); else URL.revokeObjectURL(url);
    }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [path]);
  return { state, error };
}

const loading = <p className="flex items-center gap-2 px-3 py-3 text-xs text-text-tertiary"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading from the delivered file…</p>;

/** The rows around a cited cell, exactly as stored, with the cited row and column marked. Without a row: the first rows. */
export function RowsAround({ runId, location, around: initial = 4 }: { runId: string; location: Location; around?: number }) {
  const [around, setAround] = useState(initial);
  const [sheet, setSheet] = useState(location.sheet ?? '');
  const [data, setData] = useState<Excerpt | null>(null);
  const [error, setError] = useState('');
  const box = useRef<HTMLDivElement>(null);
  const cited = useRef<HTMLTableCellElement>(null);
  useEffect(() => { setSheet(location.sheet ?? ''); setAround(initial); }, [location.sourceId, location.sheet, location.row, initial]);
  useEffect(() => {
    let alive = true;
    const query = new URLSearchParams({ around: String(around) });
    if (location.row != null) query.set('row', String(location.row));
    if (sheet) query.set('sheet', sheet);
    setError('');
    cmoFetch(`/runs/${runId}/rows/${location.sourceId}?${query}`).then(r => r.json()).then(d => { if (alive) setData(d as Excerpt); }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, [runId, location.sourceId, location.row, sheet, around]);
  // Bring the cited column into view inside the excerpt without moving the page.
  useEffect(() => {
    if (!data || !box.current || !cited.current) return;
    box.current.scrollLeft = Math.max(0, cited.current.offsetLeft - box.current.clientWidth / 2 + cited.current.clientWidth / 2);
  }, [data]);
  if (error) return <p className="px-3 py-2 text-xs text-status-critical">{error}</p>;
  if (!data) return loading;
  const column = location.column ? data.headers.indexOf(location.column) : -1;
  const missing = location.row != null && !data.rows.some(r => r.row === location.row);
  const first = data.rows[0]?.row, last = data.rows[data.rows.length - 1]?.row;
  const more = around < 25 && ((first ?? 2) > 2 || (last ?? 0) < data.total_rows);
  return (
    <div className="overflow-hidden rounded-card border border-border-hairline bg-surface" data-testid="rows-around">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-hairline bg-surface-secondary/60 px-3 py-1.5 text-[11px] text-text-tertiary">
        <span className="font-mono text-text-secondary">{location.path}</span>
        {data.sheets.length > 1 ? <label className="flex items-center gap-1">Sheet
          <select className="h-6 rounded border border-border-strong bg-surface px-1 text-[11px] text-text-primary" value={data.sheet ?? ''} onChange={e => setSheet(e.target.value)}>
            {data.sheets.map(s => <option key={s} value={s}>{s}</option>)}</select></label> : data.sheet && <span>Sheet {data.sheet}</span>}
        <span>{data.rows.length ? `Rows ${first}–${last} of ${data.total_rows}` : 'No rows here'}</span>
        {more && <button className="ml-auto text-brand-teal hover:underline" onClick={() => setAround(a => Math.min(25, a * 3))}>Show more rows</button>}
      </div>
      {data.sheet_assumed && <p className="border-b border-border-hairline bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800">The sheet was not recorded for this item. Showing “{data.sheet}”; choose another above if this is not the one.</p>}
      {missing && <p className="border-b border-border-hairline bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800">Row {location.row} is not in this {data.sheets.length ? 'sheet' : 'file'}.</p>}
      <div ref={box} className="max-h-[340px] overflow-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead><tr className="sticky top-0 z-10 bg-surface">
            <th className="sticky left-0 z-20 border-b border-r border-border-hairline bg-surface px-2 py-1.5 text-right text-[10px] font-medium text-text-muted">Row</th>
            {data.headers.map((h, i) => <th key={i} className={cn('whitespace-nowrap border-b border-border-hairline px-2.5 py-1.5 text-left font-medium text-text-secondary', i === column && 'bg-amber-100 text-amber-900')}>{h ?? `(column ${i + 1})`}</th>)}
          </tr></thead>
          <tbody>{data.rows.map(r => {
            const here = r.row === location.row;
            return <tr key={r.row} className={cn('border-b border-border-hairline last:border-0', here && 'bg-amber-50')}>
              <th className={cn('sticky left-0 border-r border-border-hairline px-2 py-1 text-right font-mono text-[10px] font-normal text-text-muted', here ? 'bg-amber-100 text-amber-900' : 'bg-surface')}>{r.row}</th>
              {data.headers.map((_, i) => <td key={i} ref={here && i === column ? cited : undefined}
                className={cn('whitespace-nowrap px-2.5 py-1 font-mono', i === column && !here && 'bg-amber-50/60', here && i === column && 'bg-amber-200 font-semibold outline outline-2 -outline-offset-2 outline-amber-500')}>
                {r.values[i] || (here && i === column ? <span className="font-sans font-normal italic text-amber-900">blank</span> : '')}</td>)}
            </tr>;
          })}</tbody>
        </table>
      </div>
      {data.columns_truncated && <p className="border-t border-border-hairline px-3 py-1.5 text-[11px] text-text-tertiary">Only the first 80 columns are shown.</p>}
    </div>
  );
}

/** One page of a delivered PDF, with the located text outlined when its position is known, and paging to look around. */
export function PageAt({ runId, location, scale }: { runId: string; location: Location; scale?: number }) {
  const [page, setPage] = useState(location.page ?? 1);
  const [zoom, setZoom] = useState(false);
  useEffect(() => { setPage(location.page ?? 1); }, [location.sourceId, location.page]);
  const { state, error } = useBlob(`/runs/${runId}/pages/${location.sourceId}/${page}${scale ? `?scale=${scale}` : ''}`);
  if (error) return <p className="px-3 py-2 text-xs text-status-critical">{error}</p>;
  if (!state) return loading;
  const width = Number(state.headers.get('X-Page-Width') ?? 1), height = Number(state.headers.get('X-Page-Height') ?? 1), pages = Number(state.headers.get('X-Page-Count') ?? 1);
  const region = page === (location.page ?? 1) ? location.region : null;
  return (
    <div className="overflow-hidden rounded-card border border-border-hairline bg-surface" data-testid="page-at">
      <div className="flex flex-wrap items-center gap-2 border-b border-border-hairline bg-surface-secondary/60 px-3 py-1.5 text-[11px] text-text-tertiary">
        <span className="font-mono text-text-secondary">{location.path}</span>
        <span>{region ? 'Located text outlined' : location.page ? 'Find the line on this page' : 'No page was recorded for this item; look through the pages'}</span>
        <span className="ml-auto flex items-center gap-1">
          <button aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="rounded p-0.5 hover:bg-surface-secondary disabled:opacity-30"><ChevronLeft className="h-3.5 w-3.5" /></button>
          Page {page} of {pages}
          <button aria-label="Next page" disabled={page >= pages} onClick={() => setPage(p => p + 1)} className="rounded p-0.5 hover:bg-surface-secondary disabled:opacity-30"><ChevronRight className="h-3.5 w-3.5" /></button>
          <button aria-label={zoom ? 'Fit page' : 'Zoom in'} onClick={() => setZoom(z => !z)} className="ml-1 rounded p-0.5 hover:bg-surface-secondary">{zoom ? <ZoomOut className="h-3.5 w-3.5" /> : <ZoomIn className="h-3.5 w-3.5" />}</button>
        </span>
      </div>
      <div className="max-h-[520px] overflow-auto bg-surface-secondary">
        <div className="relative mx-auto" style={{ width: zoom ? width * 1.5 : '100%', maxWidth: zoom ? undefined : 760 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img alt={`Page ${page} of ${location.path}`} src={state.url} className="h-auto w-full" />
          {region && <div aria-label="Located text" className="pointer-events-none absolute border-2 border-amber-500 bg-amber-200/20" style={{
            left: `${100 * Math.min(region[0], region[2]) / width}%`, top: `${100 * (region[1] > region[3] ? height - region[1] : region[1]) / height}%`,
            width: `${100 * Math.abs(region[2] - region[0]) / width}%`, height: `${100 * Math.abs(region[3] - region[1]) / height}%` }} />}
        </div>
      </div>
    </div>
  );
}

/** The part of the original file an item refers to, shown in place so the file never has to be opened elsewhere. */
export function SourceContext({ runId, location, around }: { runId: string; location: Location; around?: number }) {
  if (isTable(location.path)) return <RowsAround runId={runId} location={location} around={around} />;
  if (isPdf(location.path)) return <PageAt runId={runId} location={location} />;
  return <p className="px-3 py-2 text-xs text-text-tertiary">This kind of file cannot be shown in place yet.</p>;
}

type Preview = { kind: 'table' | 'pdf' | 'image' | 'text' | 'none'; pages?: number; text?: string; truncated?: boolean; headers?: Array<string | null>; rows?: Array<{ row: number; values: Array<string | null> }>; total_rows?: number };

/** A small look at one file: enough to tell what it is. */
export function Thumbnail({ runId, sourceId, path }: { runId: string; sourceId: string; path: string }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    cmoFetch(`/runs/${runId}/preview/${sourceId}`).then(r => r.json()).then(p => { if (alive) setPreview(p as Preview); }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [runId, sourceId]);
  const picture = useBlob(preview?.kind === 'pdf' ? `/runs/${runId}/pages/${sourceId}/1?scale=0.4` : preview?.kind === 'image' ? `/runs/${runId}/images/${sourceId}` : null);
  const frame = 'h-28 w-full overflow-hidden rounded-control border border-border-hairline bg-surface-secondary/50';
  if (failed || picture.error) return <div className={cn(frame, 'flex items-center justify-center px-2 text-center text-[11px] text-text-tertiary')}>Preview unavailable</div>;
  if (!preview) return <div className={cn(frame, 'animate-pulse')} />;
  if (preview.kind === 'table') return <div className={cn(frame, 'bg-surface')}>
    <table className="w-full table-fixed border-collapse text-[9px] leading-tight"><tbody>
      <tr className="bg-surface-secondary">{(preview.headers ?? []).slice(0, 5).map((h, i) => <th key={i} className="truncate border-b border-border-hairline px-1 py-0.5 text-left font-medium text-text-secondary">{h}</th>)}</tr>
      {(preview.rows ?? []).slice(0, 6).map(r => <tr key={r.row}>{(preview.headers ?? []).slice(0, 5).map((_, i) => <td key={i} className="truncate border-b border-border-hairline/60 px-1 py-0.5 font-mono text-text-tertiary">{r.values[i]}</td>)}</tr>)}
    </tbody></table></div>;
  if (preview.kind === 'text') return <div className={cn(frame, 'bg-surface px-2 py-1.5 text-[9px] leading-snug text-text-tertiary')}><p className="line-clamp-[8] whitespace-pre-wrap break-words">{preview.text}</p></div>;
  if (preview.kind === 'pdf' || preview.kind === 'image') return <div className={frame}>
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {picture.state ? <img alt={`First page of ${path}`} src={picture.state.url} className="h-full w-full object-cover object-top" /> : <div className="h-full animate-pulse" />}</div>;
  return <div className={cn(frame, 'flex items-center justify-center text-[11px] text-text-tertiary')}>No preview for this file type</div>;
}

/** The larger look at one file: first rows, pages, picture or text. */
export function FilePreview({ runId, sourceId, path }: { runId: string; sourceId: string; path: string }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true; setPreview(null); setError('');
    cmoFetch(`/runs/${runId}/preview/${sourceId}`).then(r => r.json()).then(p => { if (alive) setPreview(p as Preview); }).catch(e => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, [runId, sourceId]);
  const picture = useBlob(preview?.kind === 'image' ? `/runs/${runId}/images/${sourceId}` : null);
  if (error) return <p className="text-xs text-status-critical">{error}</p>;
  if (!preview) return loading;
  if (preview.kind === 'table') return <RowsAround runId={runId} location={{ sourceId, path }} around={12} />;
  if (preview.kind === 'pdf') return <PageAt runId={runId} location={{ sourceId, path, page: 1 }} />;
  if (preview.kind === 'text') return <div><pre className="max-h-[480px] overflow-auto whitespace-pre-wrap break-words rounded-card border border-border-hairline bg-surface-secondary/50 p-3 text-[12px]">{preview.text}</pre>
    {preview.truncated && <p className="mt-1 text-[11px] text-text-tertiary">Only the opening of this file is shown.</p>}</div>;
  if (preview.kind === 'image') return picture.state
    // eslint-disable-next-line @next/next/no-img-element
    ? <img alt={path} src={picture.state.url} className="max-h-[520px] w-full rounded-card border border-border-hairline object-contain" /> : loading;
  return <p className="text-xs text-text-tertiary">This file type has no preview.</p>;
}
