'use client';

import type { GuidedStep } from './GuidedConnection';
import { PointingGuide } from './shell/PointingGuide';

export type ConnectionGuideStep = GuidedStep | 'system' | 'protocol' | 'access' | 'preview' | 'ready' | 'verify' | 'unavailable';

const guidance: Record<ConnectionGuideStep, { anchor: string; title: string; body: string }> = {
  system: { anchor: 'setup-source-search', title: 'Find your system', body: 'Search for the system that holds your records, then select it. If you work from exports, choose Upload files instead.' },
  protocol: { anchor: 'setup-protocol', title: 'Choose the kind of record', body: 'Select the source family that matches your records. Have your administrator confirm the host and credential reference before continuing.' },
  access: { anchor: 'setup-access', title: 'Configure read access', body: 'Choose the site and enter the connection details your administrator approved. Saving creates a manual connection so you can test it first.' },
  preview: { anchor: 'setup-preview', title: 'Check the connection', body: 'Review the source and run a preview when available. Use the sample to check the field mapping before starting collection.' },
  ready: { anchor: 'setup-workspace', title: 'Open your workspace', body: 'Open the workspace to start using the data, or add another source.' },
  verify: { anchor: 'setup-verify', title: 'Trace a collected value', body: 'Open the record behind a value and check its source and mapping. Entries that need review are marked here.' },
  unavailable: { anchor: 'setup-unavailable', title: 'Reload the available systems', body: 'Use Try again to reload the catalog. You can also upload an authorized export if that suits your work.' },
  signin: { anchor: 'setup-signin', title: 'Use approved access', body: 'Fill in the connection details and select the site the records belong to. Use read credentials approved by your system owner.' },
  choose: { anchor: 'setup-resources', title: 'Choose what to read', body: 'Find the tags, tables, or records you want to collect, then continue to read a sample.' },
  fields: { anchor: 'setup-mapping', title: 'Check the source fields', body: 'Compare the field matches with the sample. Confirm the mapping when it looks right, then continue to collection settings.' },
  collect: { anchor: 'setup-schedule', title: 'Decide when collection runs', body: 'Choose a schedule or leave collection manual. Run first sync only when you are ready to read source records into this workspace.' },
  done: { anchor: 'setup-review', title: 'Review what arrived', body: 'Open the collected data to check the source records and see anything that needs review.' },
};

export function ConnectionSetupGuide({ step, onClose }: { step: ConnectionGuideStep; onClose: () => void }) {
  const current = guidance[step];
  return <PointingGuide label="Setup guide" anchor={current.anchor} locate narration={`${current.title}. ${current.body}`} onClose={onClose}>
    <div aria-live="polite"><h2>{current.title}</h2><p>{current.body}</p></div>
  </PointingGuide>;
}
