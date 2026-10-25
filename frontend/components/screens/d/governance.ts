// Synthetic governance data for SETTINGS-01. Hashes are produced by a non-cryptographic demo function.

export const ROLES = ['MSAT', 'Supervisor', 'QA', 'Operator', 'SysAdmin'] as const;
export const CAPABILITIES = [
  { key: 'view', label: 'View data' },
  { key: 'draft', label: 'Draft documents' },
  { key: 'propose', label: 'Propose changes' },
  { key: 'sign', label: 'Sign approvals' },
  { key: 'connectors', label: 'Configure connectors' },
  { key: 'agents', label: 'Manage agents' },
] as const;
export const SITES = ['Mesa', 'Durham', 'Basel'] as const;

export type Role = (typeof ROLES)[number];
export type Cap = (typeof CAPABILITIES)[number]['key'];
export type Site = (typeof SITES)[number];
export type Matrix = Record<Role, Record<Cap, boolean>>;

/** Segregation-of-duties rules that the UI will not allow to be changed. */
export const LOCKED: Partial<Record<Role, Partial<Record<Cap, string>>>> = {
  SysAdmin: { sign: 'Segregation of duties: system administrators cannot sign GxP approvals.' },
  Operator: { sign: 'Operators sign step execution in MES, not platform approvals.', connectors: 'Restricted to SysAdmin.' },
};

const base: Matrix = {
  MSAT: { view: true, draft: true, propose: true, sign: true, connectors: false, agents: true },
  Supervisor: { view: true, draft: true, propose: true, sign: true, connectors: false, agents: false },
  QA: { view: true, draft: true, propose: false, sign: true, connectors: false, agents: false },
  Operator: { view: true, draft: false, propose: false, sign: false, connectors: false, agents: false },
  SysAdmin: { view: true, draft: false, propose: false, sign: false, connectors: true, agents: true },
};

function clone(m: Matrix): Matrix {
  return JSON.parse(JSON.stringify(m));
}

export function initialPolicies(): Record<Site, Matrix> {
  const durham = clone(base);
  durham.MSAT.agents = false;
  const basel = clone(base);
  basel.MSAT.sign = false;
  basel.Supervisor.propose = false;
  return { Mesa: clone(base), Durham: durham, Basel: basel };
}

/** Deterministic 64-hex demo digest. NOT SHA-256; used only to illustrate hash chaining. */
export function demoHash(input: string) {
  let out = '';
  let h1 = 0x811c9dc5;
  for (let round = 0; round < 8; round++) {
    let h = h1 ^ (round * 0x9e3779b1);
    for (let i = 0; i < input.length; i++) {
      h ^= input.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    h1 = h;
    out += h.toString(16).padStart(8, '0');
  }
  return out;
}

export type AuditEntry = { seq: number; time: string; actor: string; action: string; object: string; prev: string; hash: string };

const SEED: Array<Omit<AuditEntry, 'seq' | 'prev' | 'hash'>> = [
  { time: '2026-10-19 08:26:04', actor: 'agent:msat-yield-sentry', action: 'run.start (read-only)', object: 'RUN-2026-1042' },
  { time: '2026-10-19 08:32:45', actor: 'agent:msat-yield-sentry', action: 'proposal.routed', object: 'RCP-AB014-V4.patch.02 → REV-01' },
  { time: '2026-10-19 09:05:11', actor: 'P. Natarajan', action: 'record.viewed', object: 'Q-DEV-031' },
  { time: '2026-10-19 09:40:52', actor: 'A. Rivera', action: 'memory.confirm', object: 'INV-104/m2' },
  { time: '2026-10-19 11:40:20', actor: 'agent:lab-result-watcher', action: 'notification.sent', object: 'QC-948' },
  { time: '2026-10-19 12:02:37', actor: 'R. Osei', action: 'connector.health_check', object: 'OSIsoft PI · PI-UFL-MESA-02' },
];

export const GENESIS = '0'.repeat(64);

export function chain(entries: Array<Omit<AuditEntry, 'seq' | 'prev' | 'hash'>>, startSeq: number, prev = GENESIS): AuditEntry[] {
  let p = prev;
  return entries.map((e, i) => {
    const seq = startSeq + i;
    const hash = demoHash(`${p}|${seq}|${e.time}|${e.actor}|${e.action}|${e.object}`);
    const out = { ...e, seq, prev: p, hash };
    p = hash;
    return out;
  });
}

export const AUDIT_BASE_COUNT = 38412;
export const SEED_PREV = demoHash('audit-log-mesa-seq-38406');
export const SEED_AUDIT = chain(SEED, AUDIT_BASE_COUNT - SEED.length + 1, SEED_PREV);

export function merkleRoot(hashes: string[]): string {
  if (hashes.length === 0) return GENESIS;
  let level = hashes;
  while (level.length > 1) {
    const next: string[] = [];
    for (let i = 0; i < level.length; i += 2) next.push(demoHash(level[i] + (level[i + 1] ?? level[i])));
    level = next;
  }
  return level[0];
}
