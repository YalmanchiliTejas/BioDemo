'use client';

import { useEffect, useMemo, useState } from 'react';
import { Download, FileKey2, Lock, Save, ShieldCheck, Unplug, Undo2 } from 'lucide-react';
import { Button, Callout, Card, CardBody, CardHeader, Hash, PageHeader, Pill, Segmented, Stat, StatusDot, table } from '@/components/ui';
import {
  AUDIT_BASE_COUNT, CAPABILITIES, LOCKED, ROLES, SEED_AUDIT, SITES, chain, initialPolicies, merkleRoot,
  type AuditEntry, type Cap, type Matrix, type Role, type Site,
} from '@/components/screens/d/governance';
import { ROLE_PEOPLE, useAppContext } from '@/lib/app-context';
import { cn } from '@/lib/cn';

const LIVE_EVENTS = [
  { actor: 'agent:data-intake', action: 'source.read', object: 'OSIsoft PI · PM204.FLOW_PV' },
  { actor: 'agent:maint-correlator', action: 'source.read', object: 'Maximo · WO-8819' },
  { actor: 'M. Bell', action: 'record.viewed', object: 'PM-204 equipment page' },
  { actor: 'agent:knowledge-indexer', action: 'index.update', object: 'SOP-UP-014 Rev 7' },
];

function stamp() {
  return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

export default function GovernancePage() {
  const { notify, userRole } = useAppContext();
  const [site, setSite] = useState<Site>('Mesa');
  const [saved, setSaved] = useState<Record<Site, Matrix>>(initialPolicies);
  const [policies, setPolicies] = useState<Record<Site, Matrix>>(initialPolicies);
  const [audit, setAudit] = useState<AuditEntry[]>(SEED_AUDIT);
  const [live, setLive] = useState(true);

  const cfrPart11Enforced = true;
  const airGapMode = 'ACTIVE';
  const auditLogCount = AUDIT_BASE_COUNT + (audit.length - SEED_AUDIT.length);

  const append = (items: Array<Omit<AuditEntry, 'seq' | 'prev' | 'hash'>>) =>
    setAudit((a) => {
      const last = a[a.length - 1];
      return [...a, ...chain(items, last.seq + 1, last.hash)];
    });

  useEffect(() => {
    if (!live) return;
    let i = 0;
    const h = setInterval(() => {
      append([{ time: stamp(), ...LIVE_EVENTS[i % LIVE_EVENTS.length] }]);
      i++;
    }, 7000);
    return () => clearInterval(h);
  }, [live]);

  const changes = useMemo(() => {
    const out: Array<{ site: Site; role: Role; cap: Cap; to: boolean }> = [];
    SITES.forEach((s) => ROLES.forEach((r) => CAPABILITIES.forEach((c) => {
      if (policies[s][r][c.key] !== saved[s][r][c.key]) out.push({ site: s, role: r, cap: c.key, to: policies[s][r][c.key] });
    })));
    return out;
  }, [policies, saved]);

  const toggle = (r: Role, c: Cap) =>
    setPolicies((p) => ({ ...p, [site]: { ...p[site], [r]: { ...p[site][r], [c]: !p[site][r][c] } } }));

  const save = () => {
    if (!changes.length) return;
    append(changes.map((ch) => ({ time: stamp(), actor: ROLE_PEOPLE[userRole], action: `policy.${ch.to ? 'grant' : 'revoke'}`, object: `${ch.site}/${ch.role}/${ch.cap}` })));
    setSaved(JSON.parse(JSON.stringify(policies)));
    notify(`Role access policy saved (${changes.length} change${changes.length === 1 ? '' : 's'}). Changes recorded to the audit log — demo only, no identity provider updated.`);
  };

  const root = merkleRoot(audit.map((a) => a.hash));

  const exportPackage = () => {
    const pkg = {
      notice: 'DEMO AUDIT PACKAGE. Synthetic data. Hashes are produced by a non-cryptographic demo function and do not verify any real record. Delivered as JSON (not ZIP) in this demo.',
      generatedAt: new Date().toISOString(),
      site: 'Aster Biologics · Mesa Manufacturing',
      part11: { controlsEnabled: cfrPart11Enforced, validationStatus: 'not yet validated (demo)' },
      airGapMode,
      dcsWritebackMode: 'LOCKED_READ_ONLY',
      auditLogCount,
      merkleRoot: root,
      entries: audit,
      roleAccessPolicy: saved,
    };
    const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audit-package-demo.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify('Downloaded audit-package-demo.json (demo JSON in place of a signed ZIP).', 'info');
  };

  const m = policies[site];

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="SETTINGS-01"
        crumbs={[{ label: 'Settings' }, { label: 'Governance' }]}
        title="Security, roles & GxP configuration"
        status={<Pill tone="muted">Demo configuration</Pill>}
        description="Who can do what at each site, the platform’s non-negotiable write boundary, and the tamper-evident audit trail. Designed to support 21 CFR Part 11 audit trails; validation is the customer’s responsibility and has not been performed here."
        actions={
          <>
            <Button onClick={exportPackage}><Download className="h-3.5 w-3.5" /> Export cryptographic audit package (ZIP)</Button>
            <Button variant="primary" onClick={save} disabled={!changes.length}><Save className="h-3.5 w-3.5" /> Save role access policy{changes.length ? ` (${changes.length})` : ''}</Button>
          </>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <Card>
          <CardBody>
            <div className="flex items-center gap-2">
              <FileKey2 className="h-4 w-4 text-brand-teal" aria-hidden />
              <p className="text-[13px] font-semibold text-text-primary">21 CFR Part 11 controls</p>
              <Pill tone={cfrPart11Enforced ? 'success' : 'muted'} dot>{cfrPart11Enforced ? 'Enabled' : 'Off'}</Pill>
            </div>
            <p className="mt-2 text-[12.5px] text-text-secondary">Part 11 controls enabled: e-signature meaning, re-auth, audit trail — validation status: <span className="font-semibold text-status-warning">not yet validated (demo)</span></p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <div className="flex items-center gap-2">
              <Unplug className="h-4 w-4 text-brand-teal" aria-hidden />
              <p className="text-[13px] font-semibold text-text-primary">Air-gap mode</p>
              <Pill tone="success" dot>{airGapMode}</Pill>
            </div>
            <p className="mt-2 text-[12.5px] text-text-secondary">Models and connectors run inside the site network. No outbound traffic to external model APIs; updates are imported as signed bundles.</p>
          </CardBody>
        </Card>
        <Card>
          <CardBody className="flex items-start justify-between gap-3">
            <Stat label="Audit log entries" value={auditLogCount.toLocaleString('en-US')} hint="Append-only · Mesa site" />
            <span className="flex items-center gap-1.5 text-[11px] text-text-tertiary"><StatusDot tone={live ? 'success' : 'muted'} pulse={live} />{live ? 'Live' : 'Paused'}</span>
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Role access matrix"
            subtitle="Grants apply per site. Locked cells enforce segregation of duties."
            actions={<Segmented<Site> value={site} onChange={setSite} options={SITES.map((s) => ({ value: s, label: s }))} />}
          />
          <div className={table.wrap}>
            <table className={table.root}>
              <thead>
                <tr>
                  <th className={table.th}>Role · {site}</th>
                  {CAPABILITIES.map((c) => <th key={c.key} className={cn(table.th, 'text-center')}>{c.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {ROLES.map((r) => (
                  <tr key={r} className={table.tr}>
                    <td className={cn(table.td, 'font-medium')}>{r}</td>
                    {CAPABILITIES.map((c) => {
                      const lock = LOCKED[r]?.[c.key];
                      const on = m[r][c.key];
                      const dirty = on !== saved[site][r][c.key];
                      return (
                        <td key={c.key} className={cn(table.td, 'text-center')}>
                          {lock ? (
                            <span title={lock} className="inline-flex items-center justify-center h-5 w-9 rounded-pill bg-surface-secondary border border-border-hairline text-text-muted" aria-label={`${r} ${c.label}: locked off. ${lock}`}>
                              <Lock className="h-3 w-3" />
                            </span>
                          ) : (
                            <button
                              type="button"
                              role="switch"
                              aria-checked={on}
                              aria-label={`${r} ${c.label} at ${site}`}
                              onClick={() => toggle(r, c.key)}
                              className={cn('relative inline-flex h-5 w-9 items-center rounded-pill transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-teal', on ? 'bg-brand-teal' : 'bg-slate-300', dirty && 'ring-2 ring-amber-400 ring-offset-1')}
                            >
                              <span className={cn('inline-block h-4 w-4 rounded-full bg-white shadow transition-transform', on ? 'translate-x-[18px]' : 'translate-x-0.5')} />
                            </button>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-t border-border-hairline bg-surface-secondary/40 text-[11.5px] text-text-tertiary">
            {changes.length ? (
              <>
                <span className="text-amber-700 font-medium">{changes.length} unsaved change{changes.length === 1 ? '' : 's'}</span>
                <span>({Array.from(new Set(changes.map((c) => c.site))).join(', ')})</span>
                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setPolicies(JSON.parse(JSON.stringify(saved)))}><Undo2 className="h-3 w-3" /> Discard</Button>
                <Button size="sm" variant="primary" onClick={save}>Save</Button>
              </>
            ) : (
              <span>No unsaved changes. Saving records each grant or revoke as a separate audit entry.</span>
            )}
          </div>
        </Card>

        <Card className="border-emerald-200">
          <CardHeader icon={<ShieldCheck className="h-4 w-4 text-status-success" />} title="DCS zero-writeback guardrail" actions={<Pill tone="success"><Lock className="h-3 w-3" />Locked</Pill>} />
          <CardBody className="space-y-3">
            <div className="flex items-center justify-between rounded-control border border-border-hairline bg-surface-secondary px-3 py-2">
              <span className="text-[12.5px] font-mono text-text-primary">LOCKED_READ_ONLY</span>
              <span aria-disabled="true" title="Cannot be changed in the UI" className="relative inline-flex h-5 w-9 items-center rounded-pill bg-slate-300 opacity-60 cursor-not-allowed">
                <span className="inline-block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow" />
              </span>
            </div>
            <ul className="space-y-1.5 text-[12.5px] text-text-secondary list-disc pl-5">
              <li>No user, role or agent can write to DCS, PLC or MES from this platform.</li>
              <li>Connectors are provisioned with read-only service accounts; there is no write code path to enable.</li>
              <li>Changing this requires a separate, validated integration project under site change control — not a setting.</li>
            </ul>
            <p className="text-[11.5px] text-text-tertiary">Why: process control changes are safety-critical and must go through the site’s own validated systems and approvals.</p>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Audit log · chained hashes"
          subtitle="Each entry includes the previous entry’s hash. Hashes are synthetic demo values, not SHA-256."
          actions={
            <>
              <span className="hidden md:flex items-center gap-1.5 text-[11px] text-text-tertiary">Merkle root <Hash value={root} /></span>
              <Button size="sm" variant="ghost" onClick={() => setLive((l) => !l)}>{live ? 'Pause live' : 'Resume live'}</Button>
            </>
          }
        />
        <div className={table.wrap}>
          <table className={table.root}>
            <thead>
              <tr>
                {['Seq', 'Time (UTC)', 'Actor', 'Action', 'Object', 'Prev hash → entry hash'].map((h) => <th key={h} className={table.th}>{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {[...audit].reverse().slice(0, 12).map((e) => (
                <tr key={e.seq} className={table.tr}>
                  <td className={cn(table.td, 'font-mono text-text-tertiary')}>{e.seq}</td>
                  <td className={cn(table.td, 'font-mono text-[12px] whitespace-nowrap')}>{e.time}</td>
                  <td className={cn(table.td, e.actor.startsWith('agent:') && 'font-mono text-[12px]')}>{e.actor}</td>
                  <td className={cn(table.td, 'font-mono text-[12px]')}>{e.action}</td>
                  <td className={cn(table.td, 'text-text-secondary')}>{e.object}</td>
                  <td className={cn(table.td, 'whitespace-nowrap')}><Hash value={e.prev} /> <span className="text-text-muted">→</span> <Hash value={e.hash} className="text-text-primary" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2.5 border-t border-border-hairline">
          <Callout tone="info">Showing the latest 12 of {auditLogCount.toLocaleString('en-US')} entries. The export contains the entries loaded in this session plus the Merkle root, as JSON named <span className="font-mono">audit-package-demo.json</span>.</Callout>
        </div>
      </Card>
    </div>
  );
}
