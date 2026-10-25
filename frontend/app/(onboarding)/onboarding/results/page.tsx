'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, Check, Copy, Download, FileCheck2, Flag, Unplug } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, ClaimTag, EvidenceChip, Hash, KeyValue, LinkButton, Pill, SectionLabel } from '@/components/ui';
import { BATCH_MANIFEST_HASH, GAP_INTERVAL, MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { EntityGraph } from '@/components/screens/a/EntityGraph';
import { Sparkline, StandaloneEvidence } from '@/components/screens/a/StandaloneEvidence';
import { GOAL_STORAGE_KEY, TZ_STORAGE_KEY, readSession } from '@/components/screens/a/onboarding';
import { useAppContext } from '@/lib/app-context';

const YIELD_TREND_OBSERVED = [81.2, 78.4, 75.9];
const HAS_MISSING_HISTORIAN_SPAN = true;

export default function OnboardingResultsPage() {
  const { notify } = useAppContext();
  const [goal, setGoal] = useState<string | null>(null);
  const [tz, setTz] = useState<string>('UTC');
  const [copied, setCopied] = useState(false);
  const target = MOCK_DATASET.activeCampaign.targetYieldIndex;

  useEffect(() => {
    setGoal(readSession(GOAL_STORAGE_KEY));
    setTz(readSession(TZ_STORAGE_KEY) === 'SITE' ? 'Site local (UTC−7)' : 'UTC');
  }, []);

  const copyHash = async () => {
    try {
      await navigator.clipboard.writeText(BATCH_MANIFEST_HASH);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      notify('Clipboard unavailable in this browser.', 'warning');
    }
  };

  const downloadManifest = () => {
    const manifest = {
      note: 'Synthetic demo manifest. Not a record from any real system.',
      campaign: 'CMP-26-10',
      generatedAt: '2026-10-19T16:40:00Z',
      timezoneAssumption: { field: 'EVENT_TS_RAW', value: tz },
      files: 8,
      records: 24190,
      duplicatesCollapsed: 37,
      entities: { batches: ['MES-26071', 'MES-26072', 'MES-26073'], equipment: ['BR-UP-01'], assays: ['HPLC-PROA-01', 'VICELL-VCD-02', 'OSMO-03', 'CEDEX-GLU-04'] },
      knownGaps: [{ source: 'OSIsoft PI', batch: 'MES-26073', startHour: GAP_INTERVAL.startHour, endHour: GAP_INTERVAL.endHour }],
      sha256: BATCH_MANIFEST_HASH,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'CMP-26-10_intake_manifest.json';
    a.click();
    URL.revokeObjectURL(url);
    notify('Manifest JSON downloaded (synthetic demo content).', 'info');
  };

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">Step 3 of 3 · ONB-03</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-text-primary">Your first result is ready</h1>
          <p className="mt-1 text-[13px] text-text-secondary max-w-2xl">
            24,190 records from 8 files are indexed and linked. Below is what the data shows so far, what it does not yet show, and where the gaps are.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <LinkButton href="/home" variant="secondary">Proceed to Daily Manufacturing Briefing</LinkButton>
          <LinkButton href="/workbench/AN-104" variant="primary">Open Process Analysis Workbench <ArrowRight className="h-3.5 w-3.5" aria-hidden /></LinkButton>
        </div>
      </div>

      {goal && (
        <div className="mt-4 rounded-card border border-border-hairline bg-surface px-4 py-3 text-[12.5px]">
          <span className="text-text-tertiary">Your question: </span>
          <span className="font-medium text-text-primary">“{goal}”</span>
          <p className="mt-1 text-text-secondary">The trend below is the most relevant finding we can show without a deeper analysis. Causes are not assessed at this step; the workbench is where you can test explanations against evidence.</p>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Indexed entity graph"
            subtitle="Hover a node to see what it is linked to. Links come from shared identifiers in the source records."
            icon={<FileCheck2 className="h-4 w-4" />}
            actions={<Pill tone="success" dot>Indexed</Pill>}
          />
          <CardBody>
            <EntityGraph />
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 border-t border-border-hairline pt-3">
              {[['Batches', '3', 'MES-26071/72/73'], ['Equipment', '1', 'BR-UP-01 skid'], ['Analytical assays', '4', 'LabWare tests'], ['Files', '8', '24,190 records']].map(([k, v, s]) => (
                <div key={k}>
                  <p className="text-[11px] uppercase tracking-wide text-text-tertiary font-medium">{k}</p>
                  <p className="text-lg font-semibold tabular-nums text-text-primary">{v}</p>
                  <p className="text-[11px] text-text-tertiary">{s}</p>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-text-tertiary">Assay list: <EvidenceChip id="a-lims-assay-panel" /></div>
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Yield is declining batch over batch" actions={<ClaimTag kind="observation" />} />
            <CardBody className="space-y-3">
              <div className="flex items-center gap-4">
                <Sparkline values={YIELD_TREND_OBSERVED} width={128} height={44} label="Normalized yield index: 81.2, 78.4, 75.9" />
                <ol className="text-[12px] tabular-nums space-y-0.5">
                  {MOCK_DATASET.activeCampaign.batches.map((b) => (
                    <li key={b.id} className="flex gap-2"><span className="font-mono text-text-tertiary">{b.id}</span><span className="font-semibold text-text-primary">{b.normalizedYield.toFixed(1)}</span></li>
                  ))}
                </ol>
              </div>
              <p className="text-[12.5px] text-text-secondary">
                Normalized yield index fell 5.3 points across three consecutive batches; MES-26073 is {(target - YIELD_TREND_OBSERVED[2]).toFixed(1)} below the {target.toFixed(1)} target.
              </p>
              <div className="rounded-control bg-surface-secondary px-2.5 py-2 text-[11.5px] text-text-secondary">
                <span className="font-semibold text-text-primary">This is not a root cause.</span> Three batches are too few to establish a trend statistically, and no explanation has been tested yet.
              </div>
              <div className="flex flex-wrap gap-1.5"><EvidenceChip id="ebr-mes-26073" /><EvidenceChip id="historian-up01" /></div>
            </CardBody>
          </Card>

          {HAS_MISSING_HISTORIAN_SPAN && (
            <Callout tone="warning" title="Missing historian data · MES-26073" icon={<Flag className="h-4 w-4" aria-hidden />}>
              <p>Hour {GAP_INTERVAL.startHour.toFixed(1)}–{GAP_INTERVAL.endHour.toFixed(1)} (42 min) has no PI records. The interface log shows a buffer overflow. Estimates shown in plots are marked imputed and excluded from statistics.</p>
              <div className="mt-2 flex flex-wrap gap-1.5"><EvidenceChip id="historian-gap" /><EvidenceChip id="a-pi-interface-log" /></div>
            </Callout>
          )}

          <Callout tone="neutral" title="Not yet connected: SAP ERP" icon={<Unplug className="h-4 w-4" aria-hidden />}>
            <p>Raw-material lots and order data are absent, so material-related explanations cannot be checked yet.</p>
            <div className="mt-2"><EvidenceChip id="a-sap-not-connected" /></div>
          </Callout>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader title="Batch manifest proof" subtitle="A SHA-256 digest over every ingested file and the mapping decisions you confirmed. Re-running intake on the same inputs reproduces it." />
          <CardBody className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 rounded-control border border-border-hairline bg-surface-secondary px-3 py-2">
              <Hash value={BATCH_MANIFEST_HASH} full className="break-all text-text-primary" />
              <div className="ml-auto flex gap-1.5">
                <Button size="sm" variant="ghost" onClick={copyHash} aria-label="Copy manifest hash">{copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}{copied ? 'Copied' : 'Copy'}</Button>
                <Button size="sm" variant="secondary" onClick={downloadManifest}><Download className="h-3.5 w-3.5" aria-hidden />Manifest JSON</Button>
              </div>
            </div>
            <KeyValue cols={4} items={[['Files', '8'], ['Records', '24,190'], ['Duplicates collapsed', '37'], ['EVENT_TS_RAW zone', tz]]} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Data health" />
          <CardBody className="space-y-2 text-[12.5px]">
            <SectionLabel>What you can do next</SectionLabel>
            <ul className="space-y-1.5 text-text-secondary">
              <li>Compare batches on a shared time axis and test explanations in the workbench.</li>
              <li>See today’s priorities across batches, quality and equipment in the briefing.</li>
            </ul>
            <SectionLabel className="pt-2">Coverage</SectionLabel>
            <KeyValue cols={2} items={[['Telemetry completeness', '99.7%'], ['Sources included', '5 of 6'], ['Mappings confirmed', '10 of 10 key'], ['Questions asked of you', '1']]} />
          </CardBody>
        </Card>
      </div>
      <StandaloneEvidence />
    </div>
  );
}
