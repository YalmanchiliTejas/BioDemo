'use client';

import Link from 'next/link';
import { ArrowRight, CalendarClock, ClipboardCheck, FlaskConical, Gauge, Truck, TrendingDown } from 'lucide-react';
import { Card, CardBody, CardHeader, ClaimTag, EvidenceChip, LinkButton, PageHeader, Pill, ProgressBar, Segmented, Stat, StatusDot, table, type Tone } from '@/components/ui';
import { MOCK_DATASET } from '@/fixtures/biomanufacturingData';
import { ROLE_PEOPLE, useAppContext, type UserRole } from '@/lib/app-context';
import { cn } from '@/lib/cn';

type QueueItem = {
  id: string;
  title: string;
  detail: string;
  tone: Tone;
  icon: typeof TrendingDown;
  kind: 'observation' | 'calculated' | 'recommendation';
  citation?: string;
  cta: { label: string; href: string };
  roles: UserRole[];
};

const QUEUE: QueueItem[] = [
  {
    id: 'Q1',
    title: 'Yield index on MES-26073 is 6.1 pts below the campaign target',
    detail: 'Normalized yield 75.9 vs 82.0 target (−5.3 vs MES-26071). Consecutive decline 81.2 → 78.4 → 75.9 across the campaign. Feed flow fell 14.2% after a PM-204 head-pressure spike at T+264.4h.',
    tone: 'critical',
    icon: TrendingDown,
    kind: 'calculated',
    citation: 'historian-up01',
    cta: { label: 'Open workbench', href: '/workbench/AN-104' },
    roles: ['MSAT_LEAD', 'CLEANROOM_SUPERVISOR', 'QA_REVIEWER'],
  },
  {
    id: 'Q2',
    title: 'PM-204 sanitization overlaps MES-26074 inoculation by 4.5 h',
    detail: 'CIP window on Skid BR-UP-01 collides with scheduled inoculation on Mon 26 Oct. Two resolution scenarios are drafted; neither is applied.',
    tone: 'warning',
    icon: CalendarClock,
    kind: 'observation',
    cta: { label: 'Open planning', href: '/planning' },
    roles: ['CLEANROOM_SUPERVISOR', 'MSAT_LEAD'],
  },
  {
    id: 'Q3',
    title: 'QC-948 titer result awaiting second-person review',
    detail: 'HPLC titer 3.42 g/L is out of trend (spec >3.80 g/L). Primary analyst signed; QA reviewer signature pending.',
    tone: 'warning',
    icon: FlaskConical,
    kind: 'observation',
    citation: 'lims-qc-948',
    cta: { label: 'Review result', href: '/laboratory/QC-948' },
    roles: ['QA_REVIEWER', 'MSAT_LEAD'],
  },
  {
    id: 'Q4',
    title: 'TT-006 Gate 2 blocked: Durham feed-loop PID constants unmapped',
    detail: 'Recipient site has no mapped cascade tuning for the 2000L stainless feed loop. Gate 2 cannot be cleared until engineering supplies constants.',
    tone: 'neutral',
    icon: Truck,
    kind: 'observation',
    cta: { label: 'Review transfer blocker', href: '/tech-transfer/TT-006' },
    roles: ['MSAT_LEAD'],
  },
];

const REVIEWS = [
  { id: 'ACT-2026-0891', title: 'Recipe patch RCP-AB014-V4.patch.02 · closed-loop feed cascade', owner: 'Alex Rivera', needs: 'MSAT Lead + QA Reviewer', age: '3 h', href: '/reviews/REV-01' },
  { id: 'QC-948-SO', title: 'Second-person review · HPLC titer QC-948', owner: 'M. Okafor', needs: 'QA Reviewer', age: '5 h', href: '/laboratory/QC-948' },
];

const PERSPECTIVE_COPY: Record<UserRole, string> = {
  MSAT_LEAD: 'Process performance, investigations and transfer readiness.',
  QA_REVIEWER: 'Holds, deviations and records awaiting your signature.',
  CLEANROOM_SUPERVISOR: 'Equipment, schedule conflicts and shift readiness.',
  OPERATOR: 'Use the tablet companion for step-level guidance.',
};

export default function HomePage() {
  const { userRole, setRole } = useAppContext();
  const items = QUEUE.filter((q) => q.roles.includes(userRole));
  const camp = MOCK_DATASET.activeCampaign;

  return (
    <div className="max-w-[1280px] mx-auto">
      <PageHeader
        frameId="HOME-01"
        crumbs={[{ label: 'Aster Biologics' }, { label: 'Mesa Site (UP-01)' }, { label: 'Daily briefing' }]}
        title={`Good morning, ${ROLE_PEOPLE[userRole].split(' ')[0]}`}
        description={`Monday 19 Oct briefing for ${camp.id}. ${PERSPECTIVE_COPY[userRole]}`}
        meta={<><span>Data as of 16:40 UTC</span><span>5 of 6 sources synced</span><span>Briefing drafted by MSAT Yield Sentry · reviewed by nobody yet</span></>}
        actions={
          <Segmented<UserRole>
            value={userRole === 'OPERATOR' ? 'CLEANROOM_SUPERVISOR' : userRole}
            onChange={setRole}
            options={[{ value: 'MSAT_LEAD', label: 'MSAT' }, { value: 'QA_REVIEWER', label: 'QA' }, { value: 'CLEANROOM_SUPERVISOR', label: 'Supervisor' }]}
          />
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 space-y-4">
          <Card>
            <CardHeader title="Needs attention" subtitle={`${items.length} items ranked by batch impact and time sensitivity`} />
            <ul className="divide-y divide-border-hairline">
              {items.map((q, i) => {
                const Icon = q.icon;
                return (
                  <li key={q.id} className="px-4 py-3.5 flex gap-3">
                    <span className="text-[11px] font-mono text-text-muted w-4 pt-1 tabular-nums">{i + 1}</span>
                    <span className={cn('mt-0.5 h-7 w-7 shrink-0 rounded-control flex items-center justify-center', q.tone === 'critical' ? 'bg-status-critical-bg text-status-critical' : q.tone === 'warning' ? 'bg-status-warning-bg text-status-warning' : 'bg-surface-secondary text-text-secondary')}>
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[13.5px] font-semibold text-text-primary">{q.title}</p>
                        <ClaimTag kind={q.kind} />
                      </div>
                      <p className="mt-1 text-[12.5px] text-text-secondary leading-relaxed">{q.detail}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {q.citation && <EvidenceChip id={q.citation} />}
                        <LinkButton href={q.cta.href} size="sm" variant={i === 0 ? 'primary' : 'secondary'}>
                          {q.cta.label} <ArrowRight className="h-3 w-3" />
                        </LinkButton>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card>
            <CardHeader
              title={<span className="flex items-center gap-2">Active batch <code className="font-mono text-xs text-text-secondary">MES-26073</code> <Pill tone="info" dot>In execution</Pill> <Pill tone="critical">QA hold</Pill></span>}
              subtitle="Fed-batch stationary · Day 11 of 14 · T+264.4h"
              actions={<LinkButton href="/batches/MES-26073" size="sm">Inspect active batch <ArrowRight className="h-3 w-3" /></LinkButton>}
            />
            <CardBody className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="Yield index" value="75.9" delta="−6.1 vs target" deltaTone="critical" kind="calculated" />
              <Stat label="Feed delivered" value="254.2" unit="L" delta="−25.7% vs 71" deltaTone="warning" />
              <Stat label="PM-204 head P" value="1.48" unit="bar" delta="ceiling 1.20" deltaTone="critical" kind="observation" />
              <Stat label="Data completeness" value="99.7" unit="%" hint="42-min historian gap" />
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title={`Campaign ${camp.id}`} subtitle={camp.molecule} icon={<Gauge className="h-4 w-4" />} />
            <CardBody className="space-y-3">
              {camp.batches.map((b) => (
                <div key={b.id}>
                  <div className="flex items-center justify-between text-[12.5px]">
                    <Link href={b.id === 'MES-26073' ? '/batches/MES-26073' : '/workbench/AN-104'} className="font-mono text-text-primary hover:text-brand-teal">{b.id}</Link>
                    <span className="flex items-center gap-2">
                      <span className="tabular-nums font-medium">{b.normalizedYield.toFixed(1)}</span>
                      <Pill tone={b.release === 'RELEASED' ? 'success' : 'critical'}>{b.release === 'RELEASED' ? 'Released' : 'Hold'}</Pill>
                    </span>
                  </div>
                  <ProgressBar className="mt-1.5" value={b.normalizedYield} max={90} tone={b.normalizedYield >= camp.targetYieldIndex ? 'success' : b.normalizedYield >= 78 ? 'warning' : 'critical'} label={`${b.id} yield`} />
                </div>
              ))}
              <p className="text-[11px] text-text-tertiary pt-1">Target yield index {camp.targetYieldIndex.toFixed(1)} · 2 of 3 batches released</p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Awaiting human review" subtitle="Nothing below takes effect without a named signature" icon={<ClipboardCheck className="h-4 w-4" />} />
            <ul className="divide-y divide-border-hairline">
              {REVIEWS.map((r) => (
                <li key={r.id}>
                  <Link href={r.href} className="block px-4 py-3 hover:bg-surface-secondary/60">
                    <div className="flex items-center justify-between gap-2">
                      <code className="text-[11px] font-mono text-text-tertiary">{r.id}</code>
                      <span className="text-[11px] text-text-tertiary">{r.age} ago</span>
                    </div>
                    <p className="mt-0.5 text-[13px] font-medium text-text-primary">{r.title}</p>
                    <p className="text-[11.5px] text-text-tertiary">Needs {r.needs} · from {r.owner}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Source status" actions={<Link href="/sources" className="text-xs text-brand-teal hover:underline">Details</Link>} />
            <table className={table.root}>
              <tbody>
                {[
                  ['DeltaV eBR', 'success', '2 min'],
                  ['OSIsoft PI', 'warning', '42-min gap'],
                  ['LabWare LIMS', 'success', '6 min'],
                  ['Veeva Vault QMS', 'success', '11 min'],
                  ['Maximo CMMS', 'success', '14 min'],
                  ['SAP ERP', 'neutral', 'Not connected'],
                ].map(([n, t, s]) => (
                  <tr key={n}>
                    <td className={cn(table.td, 'py-1.5')}><span className="flex items-center gap-2"><StatusDot tone={t as Tone} />{n}</span></td>
                    <td className={cn(table.td, 'py-1.5 text-right text-text-tertiary text-xs')}>{s}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </div>
  );
}
