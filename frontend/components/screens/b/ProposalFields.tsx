'use client';

import type { ReactNode } from 'react';
import { ClaimTag } from '@/components/ui';

/**
 * Structured fields every proposed action must carry: rationale, expected result, constraints,
 * owner, required approval and what evidence would change the recommendation.
 */
export function ProposalFields({ rationale, expected, constraints, owner, approval, wouldChange, status = 'Proposed · not approved · not executed' }: {
  rationale: ReactNode;
  expected: ReactNode;
  constraints: ReactNode;
  owner: ReactNode;
  approval: ReactNode;
  wouldChange: ReactNode;
  status?: string;
}) {
  const rows: Array<[string, ReactNode]> = [
    ['Rationale', rationale],
    ['Expected result', expected],
    ['Constraints', constraints],
    ['Owner', owner],
    ['Required approval', approval],
    ['Would change this proposal', wouldChange],
  ];
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <ClaimTag kind="recommendation" />
        <span className="text-[11px] text-text-tertiary">{status}</span>
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-[150px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[12.5px]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-text-tertiary sm:pt-0.5">{k}</dt>
            <dd className="text-text-secondary leading-relaxed">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
