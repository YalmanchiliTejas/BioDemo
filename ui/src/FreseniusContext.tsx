import { Badge, Card, Grid, Text, Title } from "@tremor/react";
import { FDA_RECALL_URL } from "./presentation.mjs";

const WARNING_URL = "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/fresenius-kabi-usa-llc-733107-09222026";

export default function FreseniusContext() {
  return <section aria-label="Public Fresenius facts and simulation assumptions" data-testid="fresenius-context" className="space-y-4">
    <div><h2 className="text-xl font-semibold text-gray-900">The public facts. Our hypothetical workflow.</h2>
      <p className="mt-1 text-sm text-gray-500">Two public records inform the example; the replay below is a synthetic reconstruction.</p></div>
    <Grid numItemsLg={3} className="gap-4">
      <Card>
        <Badge color="gray">Public record · 2025</Badge>
        <Title className="mt-3">Three lots really were recalled</Title>
        <Text className="mt-2">Fresenius Kabi announced a famotidine injection recall on November 6, 2025; FDA posted it November 7.</Text>
        <p className="mt-3 text-sm font-semibold text-gray-900">6133156 · 6133194 · 6133388</p>
        <Text className="mt-3">Reserve samples from one lot had out-of-specification endotoxin results. Two additional lots were included as a precaution.</Text>
        <a className="mt-4 inline-block text-sm font-medium text-emerald-700 underline" href={FDA_RECALL_URL} target="_blank" rel="noreferrer">FDA-hosted company announcement ↗</a>
        <p className="mt-1 text-xs text-gray-400">Source: announcement summary, recall reason and lot table.</p>
      </Card>
      <Card>
        <Badge color="gray">Public record · 2026</Badge>
        <Title className="mt-3">FDA documented investigation gaps</Title>
        <Text className="mt-2">The September 22, 2026 warning letter describes multiple bioburden action-limit failures in famotidine manufacturing, insufficient investigation and batch release following passing finished-product tests.</Text>
        <p className="mt-3 text-sm text-gray-600">It does not provide the lot-by-lot dates and numerical failures assigned in our simulation.</p>
        <p className="mt-2 text-sm font-medium text-gray-700">The public record does not establish the deviation closure date. Insufficient investigation does not establish that the deviation was administratively open at release.</p>
        <a className="mt-4 inline-block text-sm font-medium text-emerald-700 underline" href={WARNING_URL} target="_blank" rel="noreferrer">FDA warning letter ↗</a>
        <p className="mt-1 text-xs text-gray-400">Source: violation 1, “Endotoxin Test Failures.” Published after the 2025 recall; retrospective context, not information available to an agent in January 2025.</p>
      </Card>
      <Card>
        <Badge color="amber">Our simulation · assumed</Badge>
        <Title className="mt-3">An example of earlier escalation</Title>
        <ul className="mt-3 list-disc space-y-2 pl-4 text-sm text-gray-600">
          <li>100 synthetic batches; three assigned upstream failures using benchmark aliases 075/084/099.</li>
          <li>Assumed production, test and complaint dates, including events in 2024.</li>
          <li>Scripted January 4, 2025 cross-batch escalation, with assumed human approval and QA holds.</li>
        </ul>
        <p className="mt-3 text-sm font-medium text-amber-800">Not established: that each real recalled lot had these failures, that AI would have detected the real issue then, or that the displayed lot-days would have been avoided.</p>
      </Card>
    </Grid>
    <p className="text-xs text-gray-500">Public lot identities and published shipment dates are factual anchors. Exact simulated failures and complaint chronology are assumptions. Fresenius Kabi supplied no internal data and did not participate in, endorse or validate this demonstration. The replay demonstrates a proposed investigation workflow; measured agent executions are on the Measured benchmarks tab.</p>
  </section>;
}
