'use client';

import { useState } from 'react';
import { AlertTriangle, ArrowRight, Database, KeyRound, Lock, RefreshCw, Unplug } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, EvidenceChip, LinkButton, Modal, PageHeader, Pill, ProgressBar, SectionLabel, Stat, StatusDot, table, useDisclosure, type Tone } from '@/components/ui';
import { useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const OVERALL_COVERAGE = 98.4;
const IS_SIMULATED_DEMO_MODE = true;

type Health = 'HEALTHY' | 'DEGRADED' | 'NOT_CONNECTED';
const HEALTH: Record<Health, { label: string; tone: Tone }> = {
  HEALTHY: { label: 'Healthy', tone: 'success' },
  DEGRADED: { label: 'Data gap', tone: 'warning' },
  NOT_CONNECTED: { label: 'Not connected', tone: 'neutral' },
};

type Lineage = { table: string; records: number; mapped: number; fields: number; entity: string };
type Connector = {
  id: string;
  name: string;
  vendor: string;
  role: string;
  health: Health;
  lastSync: string;
  protocol: string;
  scope: string[];
  coverage?: number;
  citation: string;
  warning?: string;
  lineage: Lineage[];
};

const CONNECTORS: Connector[] = [
  {
    id: 'deltav', name: 'DeltaV eBR', vendor: 'Emerson', role: 'MES / electronic batch record', health: 'HEALTHY', lastSync: '2026-10-19 16:38 UTC · 2 min ago',
    protocol: 'OPC UA (read) · eBR REST export', scope: ['batch.read', 'phase_events.read', 'recipe.read'], coverage: 100, citation: 'ebr-mes-26073',
    lineage: [
      { table: 'BATCH_HEADER', records: 3, mapped: 14, fields: 14, entity: 'Batch' },
      { table: 'PHASE_EVENTS', records: 5310, mapped: 11, fields: 12, entity: 'ProcessEvent · Phase' },
      { table: 'EBR_DOCUMENTS', records: 3474, mapped: 9, fields: 9, entity: 'BatchRecord (PDF extracted)' },
    ],
  },
  {
    id: 'pi', name: 'OSIsoft PI', vendor: 'AVEVA / OSIsoft', role: 'Process historian', health: 'DEGRADED', lastSync: '2026-10-19 16:39 UTC · 1 min ago',
    protocol: 'PI Web API (read-only identity)', scope: ['points.read', 'archive.read'], coverage: 99.7, citation: 'historian-gap',
    warning: '42-minute gap on BR-UP-01 tags, Hour 182.0–182.7 of MES-26073 (PI buffer overflow). Values were never archived; re-sync cannot recover them.',
    lineage: [
      { table: 'ARCHIVE · BR-UP-01.*', records: 12443, mapped: 147, fields: 147, entity: 'Measurement' },
      { table: 'POINT_ATTRIBUTES', records: 147, mapped: 6, fields: 8, entity: 'ControlModule tag metadata' },
    ],
  },
  {
    id: 'veeva', name: 'Veeva Vault QMS', vendor: 'Veeva', role: 'Quality management', health: 'HEALTHY', lastSync: '2026-10-19 16:29 UTC · 11 min ago',
    protocol: 'Vault REST API (read-only user)', scope: ['deviations.read', 'capa.read', 'documents.read'], coverage: 100, citation: 'qms-q-dev-031',
    lineage: [
      { table: 'DEVIATIONS', records: 124, mapped: 18, fields: 22, entity: 'QualityEvent' },
      { table: 'CONTROLLED_DOCS', records: 61, mapped: 7, fields: 7, entity: 'Document' },
    ],
  },
  {
    id: 'labware', name: 'LabWare LIMS', vendor: 'LabWare', role: 'Laboratory results', health: 'HEALTHY', lastSync: '2026-10-19 16:34 UTC · 6 min ago',
    protocol: 'ODBC read replica', scope: ['sample.read', 'result.read', 'spec.read'], coverage: 100, citation: 'lims-qc-948',
    lineage: [
      { table: 'SAMPLE', records: 111, mapped: 12, fields: 15, entity: 'Sample' },
      { table: 'RESULT', records: 2205, mapped: 10, fields: 10, entity: 'SampleResult' },
    ],
  },
  {
    id: 'maximo', name: 'Maximo CMMS', vendor: 'IBM', role: 'Maintenance management', health: 'HEALTHY', lastSync: '2026-10-19 16:26 UTC · 14 min ago',
    protocol: 'Maximo REST (OSLC) read', scope: ['workorder.read', 'asset.read', 'pm.read'], coverage: 96.1, citation: 'cmms-wo-8819',
    lineage: [
      { table: 'WORKORDER', records: 486, mapped: 16, fields: 21, entity: 'MaintenanceEvent' },
      { table: 'ASSET', records: 38, mapped: 8, fields: 8, entity: 'Equipment' },
    ],
  },
  {
    id: 'sap', name: 'SAP ERP', vendor: 'SAP S/4HANA', role: 'Materials, lots and orders', health: 'NOT_CONNECTED', lastSync: 'Never',
    protocol: 'OData / RFC (not provisioned)', scope: [], citation: 'a-sap-not-connected', lineage: [],
  },
];

export default function SourcesPage() {
  const { startRun, notify, agentRunningState } = useAppContext();
  const [selected, setSelected] = useState('pi');
  const request = useDisclosure();
  const sel = CONNECTORS.find((c) => c.id === selected)!;

  const retry = (c: Connector) => {
    if (agentRunningState.isRunning) {
      notify('Another run is in progress. Retry when it finishes.', 'warning');
      return;
    }
    startRun(`Simulated re-sync · ${c.name}`, c.lineage.length + 2);
    notify(
      c.id === 'pi'
        ? 'Simulated PI re-sync started. The 42-min gap will remain: those values were never archived.'
        : `Simulated re-sync of ${c.name} started (demo mode, read-only).`,
      'info',
    );
  };

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="SOURCES-01"
        crumbs={[{ label: 'Aster Biologics' }, { label: 'Work' }, { label: 'Sources' }]}
        title="Connections & source coverage"
        status={IS_SIMULATED_DEMO_MODE ? <Pill tone="warning" dot>Simulated (Demo Mode)</Pill> : undefined}
        description="Read-only connections to your systems of record. Each source stays authoritative; this product indexes and links records without changing them."
        actions={
          <>
            <LinkButton href="/onboarding/mapping" variant="secondary">Inspect Entity Mapping Lineage</LinkButton>
            <LinkButton href="/quality" variant="primary">Inspect Quality Links <ArrowRight className="h-3.5 w-3.5" aria-hidden /></LinkButton>
          </>
        }
      />

      <Card className="mb-4">
        <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat label="Record coverage" value={OVERALL_COVERAGE.toFixed(1)} unit="%" kind="calculated" hint="Expected vs present records, 5 connected sources" />
          <Stat label="Connected" value="5" unit="of 6" hint="SAP ERP not connected" />
          <Stat label="Open data gaps" value="1" hint="PI · 42 min on MES-26073" />
          <Stat label="Write access" value="None" hint="All scopes are read-only" />
        </CardBody>
        <div className="px-4 pb-3">
          <ProgressBar value={OVERALL_COVERAGE} tone="success" label="Overall record coverage" />
          <p className="mt-1.5 text-[11px] text-text-tertiary">Coverage excludes SAP ERP, which is not connected: material and lot data are missing from analyses, not counted as covered.</p>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 self-start">
          {CONNECTORS.map((c) => {
            const h = HEALTH[c.health];
            const active = c.id === selected;
            const off = c.health === 'NOT_CONNECTED';
            return (
              <Card key={c.id} className={cn('flex flex-col', active && 'border-brand-teal ring-1 ring-brand-teal/30', off && 'bg-surface-secondary/40')}>
                <div className="px-4 pt-3 pb-3 flex-1">
                  <div className="flex items-start gap-2.5">
                    <span className={cn('h-8 w-8 rounded-control flex items-center justify-center shrink-0', off ? 'bg-surface-secondary text-text-muted' : 'bg-brand-teal-light text-brand-teal')}>
                      {off ? <Unplug className="h-4 w-4" aria-hidden /> : <Database className="h-4 w-4" aria-hidden />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-[13.5px] font-semibold text-text-primary leading-5">{c.name}</h2>
                      <p className="text-[11.5px] text-text-tertiary">{c.vendor} · {c.role}</p>
                    </div>
                    <span className="flex items-center gap-1.5 text-[11.5px] font-medium text-text-secondary"><StatusDot tone={h.tone} />{h.label}</span>
                  </div>

                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {!off && IS_SIMULATED_DEMO_MODE && <Pill tone="muted">Simulated (Demo Mode)</Pill>}
                    {!off && <Pill tone="neutral"><Lock className="h-2.5 w-2.5" aria-hidden />Read-only</Pill>}
                  </div>

                  {c.warning && (
                    <div className="mt-2.5 flex gap-2 rounded-control border border-amber-200 bg-status-warning-bg px-2.5 py-2 text-[11.5px] text-amber-800">
                      <AlertTriangle className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden /><span>{c.warning}</span>
                    </div>
                  )}

                  {off ? (
                    <p className="mt-2.5 text-[12px] text-text-secondary">No read-only service account has been provisioned. Raw-material lots, orders and genealogy from ERP are unavailable to every analysis.</p>
                  ) : (
                    <dl className="mt-2.5 space-y-1 text-[11.5px]">
                      <div className="flex justify-between gap-2"><dt className="text-text-tertiary">Last sync</dt><dd className="text-text-primary tabular-nums text-right">{c.lastSync}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-text-tertiary">Access</dt><dd className="text-text-primary text-right">{c.protocol}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-text-tertiary">Scope</dt><dd className="font-mono text-[10.5px] text-text-secondary text-right">{c.scope.join(' ')}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-text-tertiary">Coverage</dt><dd className="text-text-primary tabular-nums">{c.coverage?.toFixed(1)}%</dd></div>
                    </dl>
                  )}
                  <div className="mt-2"><EvidenceChip id={c.citation} /></div>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 border-t border-border-hairline">
                  <Button size="sm" variant={active ? 'subtle' : 'ghost'} onClick={() => setSelected(c.id)} aria-pressed={active}>
                    {off ? 'Details' : 'Lineage'}
                  </Button>
                  {off ? (
                    <Button size="sm" variant="secondary" className="ml-auto" onClick={request.onOpen}><KeyRound className="h-3 w-3" aria-hidden />Request access</Button>
                  ) : (
                    <Button size="sm" variant="secondary" className="ml-auto" onClick={() => retry(c)} aria-label={`Retry sync for ${c.name}`}>
                      <RefreshCw className="h-3 w-3" aria-hidden />Retry sync
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>

        <Card className="self-start xl:sticky xl:top-4">
          <CardHeader title={`Data lineage · ${sel.name}`} subtitle="Source tables, records indexed and fields mapped to canonical entities" />
          {sel.lineage.length === 0 ? (
            <CardBody className="space-y-3">
              <Callout tone="neutral" title="Nothing indexed from this source">
                Analyses that depend on material lots or purchase orders will show these inputs as unknown rather than assume them.
              </Callout>
              <SectionLabel>To connect</SectionLabel>
              <ol className="list-decimal pl-4 space-y-1 text-[12.5px] text-text-secondary">
                <li>ERP owner issues a read-only OData service user.</li>
                <li>IT security approves the network path (no inbound access needed).</li>
                <li>Mappings for materials and lots are proposed for your confirmation.</li>
              </ol>
            </CardBody>
          ) : (
            <>
              <div className={table.wrap}>
                <table className={table.root}>
                  <thead>
                    <tr>
                      <th className={table.th}>Table</th>
                      <th className={cn(table.th, 'text-right')}>Records</th>
                      <th className={cn(table.th, 'text-right')}>Mapped</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sel.lineage.map((l) => (
                      <tr key={l.table} className={table.tr}>
                        <td className={table.td}>
                          <code className="font-mono text-[11.5px] text-text-primary">{l.table}</code>
                          <p className="text-[10.5px] text-text-tertiary">→ {l.entity}</p>
                        </td>
                        <td className={cn(table.td, 'text-right')}>{l.records.toLocaleString()}</td>
                        <td className={cn(table.td, 'text-right')}>
                          <span className={l.mapped < l.fields ? 'text-status-warning font-medium' : ''}>{l.mapped}/{l.fields}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <CardBody className="space-y-2 text-[11.5px] text-text-tertiary">
                <p>
                  {sel.lineage.reduce((s, l) => s + l.records, 0).toLocaleString()} records ·{' '}
                  {sel.lineage.reduce((s, l) => s + (l.fields - l.mapped), 0)} unmapped fields (kept in source context, not used in calculations).
                </p>
                {sel.id === 'pi' && <p className="text-amber-700">Interface log for the gap: <EvidenceChip id="a-pi-interface-log" /></p>}
                <LinkButton href="/onboarding/mapping" size="sm" variant="ghost" className="-ml-2">Review field mappings <ArrowRight className="h-3 w-3" aria-hidden /></LinkButton>
              </CardBody>
            </>
          )}
        </Card>
      </div>

      <Modal
        open={request.open}
        onClose={request.onClose}
        title="Request SAP ERP read-only access"
        footer={
          <>
            <Button variant="ghost" onClick={request.onClose}>Cancel</Button>
            <Button variant="primary" onClick={() => { notify('Demo only: no access request was sent to SAP owners.', 'info'); request.onClose(); }}>Draft request</Button>
          </>
        }
      >
        <div className="space-y-2 text-[13px] text-text-secondary">
          <p>This drafts a request to your ERP system owner for a <span className="font-medium text-text-primary">read-only</span> service account limited to material master, batch/lot and process order data for site Mesa.</p>
          <p>No write, posting or goods-movement permissions are requested. The request must be approved by the system owner through your existing access process.</p>
        </div>
      </Modal>
    </div>
  );
}
