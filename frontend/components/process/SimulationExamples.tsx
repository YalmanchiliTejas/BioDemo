'use client';

import { ArrowRight, Loader2 } from 'lucide-react';

export type ExampleId = 'transfer' | 'measured-capacity' | 'deviation' | 'pre-transfer';
export type Example = {
  id: ExampleId; question: string; uses: string; shows: string[]; read: string[];
  /** Needs the synthetic model configurations that only a demo workspace has. */
  demoOnly?: boolean;
};

/** Worked examples: each is a real calculation on published or synthetic inputs, started with one click. */
export const EXAMPLES: Example[] = [
  { id: 'transfer', question: 'Will this freeze-drying cycle run on the receiving dryer?',
    uses: 'A published formulation and cycle, and a receiving dryer whose vapour capacity has not been measured (assumed 0.65 kg/h).',
    shows: ['The sending cycle, a direct transfer and five adjusted settings, side by side', 'Product temperature against the −28 °C limit', 'The experiments to run before relying on the result'],
    read: ['Operating comparisons: which settings finish within the temperature and vapour limits.', 'Product temperature: how close each setting comes to the −28 °C limit.',
      'Recommendation and verification: the proposed setting, and what must be measured before it is used.'] },
  { id: 'measured-capacity', question: 'How much does one unmeasured number change the answer?',
    uses: 'The same transfer, with the published 1.49 kg/h vapour capacity in place of the assumed 0.65 kg/h.',
    shows: ['The same comparison under the measured value', 'Which settings change from unworkable to workable, if any', 'Why characterising the dryer comes before choosing a setting'],
    read: ['Minimum vapour headroom: compare it with the first example.', 'Operating comparisons: see whether the assessment of each setting changed.',
      'Equipment and utility boundary: which equipment values are measured and which are assumed.'] },
  { id: 'deviation', question: 'A run looks wrong at hour 6. What explains it, and what next?',
    uses: 'A synthetic run in progress, with product temperature readings available up to hour 6 only.',
    shows: ['Three explanations tested against the readings so far', 'Forecasts for keeping or changing the shelf temperature', 'A plain statement when the readings cannot support a recommendation'],
    read: ['Deviation investigation: how well each explanation fits, and which ones the readings cannot tell apart.', 'Operating comparisons: the forecast for each shelf temperature from hour 6 on.',
      'Recommendation and verification: whether an option is recommended, and the measurement that would settle it.'] },
  { id: 'pre-transfer', demoOnly: true, question: 'Can the receiving reactor keep yield and impurity within limits?',
    uses: 'A synthetic batch reaction moved to a larger vessel whose jacket heat transfer has not been measured (checked over ±30 %).',
    shows: ['Where the receiving equipment falls short of what the recipe needs', 'A verdict for yield and for impurity, with what each rests on', 'The measurement that would settle an inconclusive verdict'],
    read: ['Equipment capability: what the receiving vessel cannot do, and by how much.', 'Verdicts: each says whether it rests on real batches, on the model over the stated range, or is only indicative.',
      'Next measurement: the input whose uncertainty matters most.'] },
];

export function SimulationExamples({ demo, busy, running, onRun }: { demo: boolean; busy: boolean; running: ExampleId | null; onRun: (example: Example) => void }) {
  const examples = EXAMPLES.filter(e => demo || !e.demoOnly);
  return (
    <section className="rounded-2xl border border-border-hairline bg-white" aria-labelledby="simulation-purpose" data-testid="simulation-examples">
      <div className="border-b border-border-hairline px-6 py-5">
        <h2 id="simulation-purpose" className="font-display text-[20px] font-light text-ink">What simulation is for</h2>
        <p className="mt-1.5 max-w-3xl text-[13.5px] leading-6 text-text-secondary">
          Ask a process model a “what if” before spending a batch on it: whether a recipe will run on different equipment, how sensitive the result is to a value nobody has measured, or which explanation fits a run that is going wrong.
          Every result states its inputs, what was measured and what was assumed, and the experiments that would confirm it. It is a basis for an engineering review, never an approval to run.
        </p>
      </div>
      <div className="px-6 pb-2 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Start with an example</p>
        <p className="mt-0.5 text-xs text-text-tertiary">Each one runs a real calculation in a few seconds on published or synthetic inputs. Change the inputs afterwards to explore.</p>
      </div>
      <ul className={`grid gap-3 px-4 pb-5 pt-2 md:grid-cols-2 ${examples.length > 3 ? 'xl:grid-cols-4' : 'xl:grid-cols-3'}`}>
        {examples.map(example => (
          <li key={example.id} className="flex flex-col rounded-card border border-border-hairline p-4">
            <h3 className="text-[14px] font-medium leading-5 text-ink">{example.question}</h3>
            <p className="mt-2 text-xs leading-5 text-text-secondary">{example.uses}</p>
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">You get</p>
            <ul className="mt-1 flex-1 list-disc space-y-0.5 pl-4 text-xs leading-5 text-text-secondary">{example.shows.map(s => <li key={s}>{s}</li>)}</ul>
            <button type="button" disabled={busy} onClick={() => onRun(example)} data-example={example.id}
              className="mt-4 inline-flex items-center justify-center gap-1.5 rounded-control bg-brand-teal px-3 py-2 text-[13px] font-medium text-white hover:bg-brand-teal-dark disabled:opacity-50">
              {running === example.id ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />Running…</> : <>Run this example<ArrowRight className="h-3.5 w-3.5" /></>}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Shown above the results of an example: where to look, in order. */
export function ExampleReadingGuide({ example, onDismiss }: { example: Example; onDismiss: () => void }) {
  return (
    <section className="rounded-card border border-brand-teal/30 bg-brand-teal-light/40 px-5 py-4" aria-label="How to read this example" data-testid="example-guide">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">Example</p>
          <h3 className="text-[15px] font-medium text-ink">{example.question}</h3>
        </div>
        <button type="button" onClick={onDismiss} className="text-xs text-text-tertiary hover:text-ink">Hide</button>
      </div>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-[13px] leading-6 text-text-secondary">{example.read.map(r => <li key={r}>{r}</li>)}</ol>
      <p className="mt-2 text-xs text-text-tertiary">To use your own process, replace the inputs below, or attach your own characterisation records in the model library.</p>
    </section>
  );
}
