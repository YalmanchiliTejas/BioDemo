'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Boxes, FilePlus2, Lock, Search, SearchX, Sparkles } from 'lucide-react';
import { Button, Callout, Card, CardHeader, ClaimTag, EvidenceChip, Hash, LinkButton, PageHeader, Pill, SectionLabel } from '@/components/ui';
import { CITATIONS } from '@/fixtures/biomanufacturingData';
import { ANSWER_STATEMENTS, KNOWLEDGE_DOCS, SEARCH_GAPS, scoreDoc, tokenize, type GxpClass, type KnowledgeDoc } from '@/components/screens/d/knowledge';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const DEFAULT_QUERY = 'feed-rate deviations after calibration PM-204';
const SYSTEMS: KnowledgeDoc['system'][] = ['Documentum', 'Maximo CMMS', 'Veeva Vault QMS', 'DeltaV eBR', 'LabWare LIMS'];
const GXP: GxpClass[] = ['GMP-critical', 'GMP', 'Non-GxP reference'];
const EQUIPMENT = ['PM-204', 'PM-201', 'BR-UP-01', 'BR-UP-02'];

function toggle<T>(list: T[], v: T) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export default function KnowledgePage() {
  const router = useRouter();
  const { notify } = useAppContext();
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [submitted, setSubmitted] = useState(DEFAULT_QUERY);
  const [searching, setSearching] = useState(false);
  const [systems, setSystems] = useState<string[]>([]);
  const [gxp, setGxp] = useState<string[]>([]);
  const [equip, setEquip] = useState<string[]>([]);

  const run = () => {
    setSearching(true);
    setSubmitted(query.trim());
    setTimeout(() => setSearching(false), 450);
  };

  const textMatches = useMemo(() => {
    const tokens = tokenize(submitted);
    return KNOWLEDGE_DOCS.map((d) => ({ d, score: tokens.length ? scoreDoc(d, tokens, CITATIONS[d.citationId]?.rawExcerpt ?? '') : 1 }))
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score);
  }, [submitted]);

  const results = useMemo(
    () => textMatches.filter(({ d }) =>
      (!systems.length || systems.includes(d.system)) &&
      (!gxp.length || gxp.includes(d.gxp)) &&
      (!equip.length || d.equipment.some((e) => equip.includes(e)))),
    [textMatches, systems, gxp, equip],
  );

  const visibleIds = new Set(results.map((r) => r.d.citationId));
  const statements = ANSWER_STATEMENTS.filter((s) => s.sources.every((id) => visibleIds.has(id)));
  const groundedSourcesCount = new Set(statements.flatMap((s) => s.sources)).size;
  const facetCount = (pred: (d: KnowledgeDoc) => boolean) => textMatches.filter(({ d }) => pred(d)).length;
  const anyFacet = systems.length + gxp.length + equip.length > 0;

  const citeInDraft = () => {
    notify('SOP-UP-014 Rev 7 §7.2 citation added to draft DOC-UP01-03 (demo; the draft is not a controlled record until approved).');
    router.push('/documents/DOC-UP01-03');
  };

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="KNOW-01"
        crumbs={[{ label: 'Platform' }, { label: 'Knowledge' }]}
        title="Knowledge search"
        status={<Pill tone="muted">Read-only index · 5 systems</Pill>}
        description="Search SOPs, maintenance records, deviations, batch records and lab results together. Answers are assembled only from the excerpts shown below; open any citation to read the source."
        meta={<><span>Index refreshed 08:40 UTC by Knowledge Indexer</span><span>Documentum · Maximo · Veeva Vault · DeltaV · LabWare</span><span>Permissions applied at query time</span></>}
        actions={
          <>
            <LinkButton href="/batches/MES-26073"><Boxes className="h-3.5 w-3.5" /> Inspect batch record</LinkButton>
            <Button variant="primary" onClick={citeInDraft}><FilePlus2 className="h-3.5 w-3.5" /> Cite in controlled draft</Button>
          </>
        }
      />

      <Card className="mb-4">
        <form className="flex flex-wrap items-center gap-2 p-3" onSubmit={(e) => { e.preventDefault(); run(); }} role="search">
          <label className="relative flex-1 min-w-[260px]">
            <span className="sr-only">Search query</span>
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" aria-hidden />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a question or search records, e.g. tubing life PM-204"
              className="w-full h-10 pl-9 pr-3 rounded-control border border-border-strong bg-surface text-[14px] focus:outline-none focus:ring-2 focus:ring-brand-teal"
            />
          </label>
          <Button type="submit" variant="primary" size="lg" disabled={searching}>{searching ? 'Searching…' : 'Search'}</Button>
          {submitted !== DEFAULT_QUERY && (
            <Button size="lg" variant="ghost" onClick={() => { setQuery(DEFAULT_QUERY); setSubmitted(DEFAULT_QUERY); }}>Reset example</Button>
          )}
        </form>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-4">
        <Card className="self-start">
          <div className="flex items-center justify-between px-3 py-2.5 border-b border-border-hairline">
            <SectionLabel>Filters</SectionLabel>
            {anyFacet && <button className="text-[11.5px] text-brand-teal hover:underline" onClick={() => { setSystems([]); setGxp([]); setEquip([]); }}>Clear</button>}
          </div>
          <Facet title="System of record" options={SYSTEMS} selected={systems} onToggle={(v) => setSystems((s) => toggle(s, v))} count={(v) => facetCount((d) => d.system === v)} />
          <Facet title="GxP class" options={GXP} selected={gxp} onToggle={(v) => setGxp((s) => toggle(s, v))} count={(v) => facetCount((d) => d.gxp === v)} />
          <Facet title="Equipment tag" options={EQUIPMENT} selected={equip} onToggle={(v) => setEquip((s) => toggle(s, v))} count={(v) => facetCount((d) => d.equipment.includes(v))} mono />
        </Card>

        <div className={cn('min-w-0 space-y-4 transition-opacity', searching && 'opacity-50')}>
          <Card>
            <CardHeader
              icon={<Sparkles className="h-4 w-4" />}
              title="Synthesized answer — every statement cited; verify before use"
              subtitle={<span>Query <span className="font-mono text-text-secondary">“{submitted || '(empty)'}”</span> · grounded in {groundedSourcesCount} source{groundedSourcesCount === 1 ? '' : 's'} from the results below</span>}
              actions={<Pill tone="muted">Not a QA determination</Pill>}
            />
            <div className="p-4 space-y-3">
              {statements.length === 0 ? (
                <p className="text-[13px] text-text-secondary">No grounded answer can be assembled from the visible results. Adjust the query or filters; the system will not answer without a citable source.</p>
              ) : (
                <ol className="space-y-2.5">
                  {statements.map((s, i) => (
                    <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-text-primary">
                      <span className="text-[11px] font-mono text-text-muted w-4 pt-0.5 tabular-nums">{i + 1}</span>
                      <p className="min-w-0">
                        <ClaimTag kind="observation" className="mr-1.5 align-middle" />
                        {s.text} {s.sources.map((id) => <EvidenceChip key={id} id={id} className="ml-0.5" />)}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
              <div className="rounded-control border border-dashed border-border-strong bg-surface-secondary/50 px-3 py-2.5">
                <p className="flex items-center gap-1.5 text-[12px] font-semibold text-text-primary"><SearchX className="h-3.5 w-3.5" aria-hidden /> Not found / gaps</p>
                <ul className="mt-1.5 space-y-1 text-[12.5px] text-text-secondary list-disc pl-5">
                  {SEARCH_GAPS.map((g) => <li key={g}>{g}</li>)}
                </ul>
              </div>
            </div>
          </Card>

          {submitted && (
            <Callout tone="neutral" icon={<Lock className="h-4 w-4" />} title="2 results hidden: you lack access to Basel QMS"
              action={<Button size="sm" onClick={() => notify('Access request drafted for the Basel QMS owner (demo — no request sent).', 'info')}>Request access</Button>}>
              Matching records exist in the Basel Veeva Vault tenant. Titles and content are withheld; they are not used in the answer above.
            </Callout>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel>{results.length} result{results.length === 1 ? '' : 's'} · ranked by term match</SectionLabel>
              {anyFacet && <span className="text-[11.5px] text-text-tertiary">{textMatches.length - results.length} hidden by filters</span>}
            </div>
            {results.length === 0 && (
              <Card><p className="p-6 text-center text-[13px] text-text-tertiary">No indexed records match “{submitted}” with the current filters.</p></Card>
            )}
            <ul className="space-y-3">
              {results.map(({ d }) => {
                const c = CITATIONS[d.citationId];
                const isSop = d.citationId === 'sop-up-014';
                const isBatch = d.citationId === 'ebr-mes-26073';
                return (
                  <li key={d.citationId}>
                    <Card className={cn(isSop && 'border-cyan-200')}>
                      <div className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Pill tone="info">{d.system}</Pill>
                          <Pill tone={d.gxp === 'GMP-critical' ? 'warning' : d.gxp === 'GMP' ? 'neutral' : 'muted'}>{d.gxp}</Pill>
                          {d.equipment.map((e) => <code key={e} className="text-[11px] font-mono text-text-tertiary">{e}</code>)}
                          <span className="ml-auto text-[11.5px] text-text-tertiary">{d.updated}</span>
                        </div>
                        <p className="mt-1.5 text-[13.5px] font-semibold text-text-primary">{d.title}</p>
                        {c && (
                          <pre className="mt-2 whitespace-pre-wrap break-words text-[11.5px] leading-relaxed font-mono text-text-primary bg-surface-secondary border border-border-hairline rounded-control p-2.5">{c.rawExcerpt}</pre>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <EvidenceChip id={d.citationId} label="Open source" />
                          {c && <Hash value={c.sha256Hash} />}
                          <span className="ml-auto flex gap-2">
                            {isSop && <Button size="sm" variant="primary" onClick={citeInDraft}><FilePlus2 className="h-3 w-3" /> Cite in controlled draft</Button>}
                            {isBatch && <LinkButton size="sm" href="/batches/MES-26073">Inspect batch record</LinkButton>}
                            {!isBatch && d.href && <LinkButton size="sm" variant="ghost" href={d.href}>Open record</LinkButton>}
                          </span>
                        </div>
                      </div>
                    </Card>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function Facet({ title, options, selected, onToggle, count, mono }: { title: string; options: string[]; selected: string[]; onToggle: (v: string) => void; count: (v: string) => number; mono?: boolean }) {
  return (
    <fieldset className="p-3 border-b border-border-hairline last:border-b-0">
      <legend className="sr-only">{title}</legend>
      <SectionLabel>{title}</SectionLabel>
      <ul className="mt-1.5 space-y-0.5">
        {options.map((o) => {
          const n = count(o);
          return (
            <li key={o}>
              <label className={cn('flex items-center gap-2 px-1.5 py-1 rounded cursor-pointer hover:bg-surface-secondary text-[12.5px]', selected.includes(o) && 'bg-brand-teal-light/60', n === 0 && !selected.includes(o) && 'opacity-50')}>
                <input type="checkbox" checked={selected.includes(o)} onChange={() => onToggle(o)} className="accent-[#0e7490]" />
                <span className={cn('flex-1 truncate text-text-primary', mono && 'font-mono text-[12px]')}>{o}</span>
                <span className="text-[11px] text-text-muted tabular-nums">{n}</span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}
