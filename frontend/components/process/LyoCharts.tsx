'use client';

import type { ReactNode } from 'react';
import data from '@/data/lyo-study.json';

export const agentArms = [
  {key:'A', label:'Agent', color:'#64748b'},
  {key:'C', label:'Agent + revised model', color:'#0e7490'},
] as const;
export type Cohort = 'primary' | 'sensitivity';
export type Task = 'forecast' | 'pretransfer';
export const format = (value:number, digits=2) => value.toLocaleString('en-US',{maximumFractionDigits:digits});
export const eyebrow = 'text-[11px] font-semibold uppercase tracking-[.14em] text-text-tertiary';

export function Figure({title,description,note,children}:{title:string;description?:string;note:ReactNode;children:ReactNode}) {
  return <figure className="min-w-0 rounded-xl border border-border-hairline bg-surface p-5 sm:p-7">
    <h3 className="text-base font-semibold tracking-tight">{title}</h3>
    {description && <p className="mt-2 text-xs leading-5 text-text-secondary">{description}</p>}
    <div className="my-7">{children}</div>
    <figcaption className="border-t border-border-hairline pt-4 text-xs leading-5 text-text-secondary">{note}</figcaption>
  </figure>;
}

export function Bars({rows,max,unit}:{rows:{label:string;value:number;color:string;detail?:string}[];max:number;unit:string}) {
  return <div role="img" aria-label={rows.map(r=>`${r.label}: ${r.detail??`${format(r.value)} ${unit}`}`).join('; ')+'. Axis starts at zero.'}>
    <div className="space-y-6">{rows.map(row=><div key={row.label}>
      <div className="mb-2 flex flex-wrap justify-between gap-2 text-xs"><span className="text-text-secondary">{row.label}</span><strong className="tabular-nums">{row.detail??`${format(row.value)} ${unit}`}</strong></div>
      <div className="h-7 overflow-hidden rounded-sm bg-surface-secondary"><div className="h-full rounded-r-sm" style={{width:`${row.value/max*100}%`,background:row.color}}/></div>
    </div>)}</div><div className="mt-3 flex justify-between text-[10px] text-text-tertiary"><span>0</span><span>{format(max)} {unit}</span></div>
  </div>;
}

const outcomes = [
  {key:'feasible_selections',label:'Feasible',color:'#0e7490'},
  {key:'unsafe_selections',label:'Unsafe',color:'#b45309'},
  {key:'characterize',label:'Characterize',color:'#a78bfa'},
  {key:'failed',label:'No valid submission',color:'#cbd5e1'},
] as const;

export function OutcomeChart({cohort}:{cohort:Cohort}) {
  const groups=data.cohorts[cohort].groups;
  return <div>
    <div className="space-y-6">{agentArms.map(arm=>{
      const group=groups[arm.key].all;
      return <div key={arm.key} role="img" aria-label={`${arm.label}: ${outcomes.map(o=>`${group[o.key]} ${o.label}`).join(', ')}; ${group.planned} sessions.`}>
        <div className="mb-3 flex flex-wrap justify-between gap-2 text-xs"><span className="font-medium">{arm.label}</span><strong className="tabular-nums text-brand-teal">{group.feasible_selections}/{group.planned} feasible</strong></div>
        <div className="grid grid-cols-12 gap-1.5" aria-hidden="true">{outcomes.flatMap(o=>Array.from({length:group[o.key]},(_,i)=><span key={`${o.key}-${i}`} title={o.label} className="aspect-square rounded-sm" style={{background:o.color}}/>))}</div>
      </div>;
    })}</div>
    <div className="mt-5 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-text-secondary">{outcomes.map(o=><span key={o.key}><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm" style={{background:o.color}}/>{o.label}</span>)}</div>
    <details className="mt-4 text-xs"><summary className="cursor-pointer text-brand-teal underline underline-offset-4">Read the outcome counts</summary><div className="mt-3 overflow-x-auto"><table className="w-full text-left text-[11px]"><caption className="sr-only">All session outcomes, including failures</caption><thead><tr><th scope="col" className="py-2 pr-3">Outcome</th>{agentArms.map(a=><th scope="col" className="py-2 pr-3" key={a.key}>{a.label}</th>)}</tr></thead><tbody>{outcomes.map(o=><tr key={o.key} className="border-t border-border-hairline"><th scope="row" className="py-2 pr-3 font-normal">{o.label}</th>{agentArms.map(a=><td className="py-2" key={a.key}>{groups[a.key].all[o.key]}</td>)}</tr>)}</tbody></table></div></details>
  </div>;
}

export function BudgetChart() {
  const y=(value:number)=>170-value/12*140;
  return <svg viewBox="0 0 480 240" className="w-full" role="img" aria-label="Same six cases and two tasks: agent submissions rose from 3 of 12 to 8 of 12; agent plus revised model remained 12 of 12. Budget and submission policy changed together.">
    {[0,4,8,12].map(n=><g key={n}><path d={`M65 ${y(n)}H405`} stroke="#e2e8f0"/><text x="48" y={y(n)+4} textAnchor="end" fontSize="11" fill="#64748b">{n}</text></g>)}
    {agentArms.map(arm=>{const b=data.budget[arm.key];return <g key={arm.key}><path d={`M100 ${y(b.primary)}L365 ${y(b.sensitivity)}`} stroke={arm.color} strokeWidth="3"/><circle cx="100" cy={y(b.primary)} r="5" fill={arm.color}/><circle cx="365" cy={y(b.sensitivity)} r="5" fill={arm.color}/><text x="87" y={y(b.primary)-11} textAnchor="end" fill={arm.color} fontSize="12" fontWeight="600">{b.primary}/12</text><text x="378" y={y(b.sensitivity)-11} fill={arm.color} fontSize="12" fontWeight="600">{b.sensitivity}/12</text></g>;})}
    <text x="100" y="197" textAnchor="middle" fontSize="11" fill="#475569">Original protocol</text><text x="100" y="214" textAnchor="middle" fontSize="10" fill="#64748b">4 calls · 120 seconds</text>
    <text x="365" y="197" textAnchor="middle" fontSize="11" fill="#475569">Follow-up protocol</text><text x="365" y="214" textAnchor="middle" fontSize="10" fill="#64748b">8 calls · 240 seconds</text>
  </svg>;
}

export function TemperatureChart() {
  const x=(h:number)=>52+h/42*566;
  const y=(t:number)=>220-(t+46)/20*190;
  function path(series:{time_h:number;temperature_c:number|null}[]) {
    let active=false;
    return series.map(p=>{if(p.temperature_c===null){active=false;return '';}const d=`${active?'L':'M'}${x(p.time_h).toFixed(2)},${y(p.temperature_c).toFixed(2)}`;active=true;return d;}).join(' ');
  }
  return <svg viewBox="0 0 650 285" className="w-full" role="img" aria-label="Illustrative hidden synthetic outcome: the hottest active vial crosses minus28 degrees Celsius on KEEP at30.5 hours. The selected minus22-degree shelf alternative stays below the limit and completes at40.08 hours. Early observations end at6 hours.">
    <rect x={x(0)} y="30" width={x(6)-x(0)} height="190" fill="#f1f5f9"/>
    {[-45,-40,-35,-30].map(t=><g key={t}><path d={`M52 ${y(t)}H618`} stroke="#e2e8f0"/><text x="41" y={y(t)+4} textAnchor="end" fontSize="10" fill="#64748b">{t}</text></g>)}
    {[0,6,12,24,36,42].map(h=><text key={h} x={x(h)} y="242" textAnchor="middle" fontSize="10" fill="#64748b">{h}</text>)}
    <path d={`M52 ${y(-28)}H618`} stroke="#b45309" strokeDasharray="5 4"/><text x="617" y={y(-28)-8} textAnchor="end" fill="#92400e" fontSize="10">−28°C critical limit</text>
    <path d={path(data.example.series.keep)} fill="none" stroke="#64748b" strokeWidth="2.5"/>
    <path d={path(data.example.series.warm)} fill="none" stroke="#0e7490" strokeWidth="2.5"/>
    <text x="52" y="18" fontSize="10" fill="#64748b">Hottest still-drying population (°C)</text><text x="335" y="266" textAnchor="middle" fontSize="11" fill="#64748b">Elapsed time (hours)</text>
    <path d={`M${x(6)} 30V220`} stroke="#94a3b8" strokeDasharray="3 3"/><text x={x(6)+7} y="201" fontSize="9" fill="#64748b">Observation cutoff</text>
  </svg>;
}
