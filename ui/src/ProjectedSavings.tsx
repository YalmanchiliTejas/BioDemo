import { useState } from "react";
import { BarChart, Card, Text, Title } from "@tremor/react";

type Row = { metric: string; Today: number; "With agent": number };
type Props = { projection: { hours: Row[]; assumptions: string } };

export default function ProjectedSavings({ projection }: Props) {
  const [deviations, setDeviations] = useState(100);
  const [hours, setHours] = useState(10);
  const [rate, setRate] = useState(120);
  const [share, setShare] = useState(0);
  const savedHours = deviations * hours * share / 100;
  const timing = projection.hours.filter(row => !row.metric.startsWith("Engineer")).map(row => ({
    metric: row.metric, "Assumed baseline": row.Today, "Assumed assistance": row["With agent"],
  }));
  return <Card>
    <Title>Planning sandbox · savings are unmeasured</Title>
    <Text>Every input below is an illustrative assumption, not an industry average or a measured Lotic result. Calendar delays do not establish labor savings. Use pilot measurements before making a business case.</Text>
    <div className="mt-5 grid gap-5 lg:grid-cols-2">
      <div className="rounded-lg border border-gray-200 p-4">
        {[
          { label: "Assumed investigations per year", value: deviations, min: 0, max: 3000, step: 50, change: setDeviations },
          { label: "Assumed labor hours per investigation", value: hours, min: 0, max: 100, step: 1, change: setHours },
          { label: "Assumed labor cost per hour ($)", value: rate, min: 0, max: 300, step: 5, change: setRate },
          { label: "Assumed labor reduction (%)", value: share, min: 0, max: 100, step: 1, change: setShare },
        ].map(input => <label key={input.label} className="mb-4 block text-sm text-gray-600">{input.label}: <b>{input.value}</b>
          <input aria-label={input.label} type="range" min={input.min} max={input.max} step={input.step} value={input.value} onChange={event => input.change(Number(event.target.value))} className="mt-1 w-full accent-emerald-600" />
        </label>)}
        <p className="text-sm text-gray-700">Under these inputs only: <b>{savedHours.toLocaleString()} labor hours/year</b> and <b>${(savedHours * rate).toLocaleString()}/year</b> modeled gross labor value.</p>
        <p className="mt-2 text-xs text-gray-500">Investigations × labor hours × assumed reduction. This is not net savings: setup, source review, corrections, coordination, inference and ongoing operation costs are excluded. Zero assumed reduction is the default; no reduction has been measured.</p>
      </div>
      <div>
        <p className="text-sm font-medium text-gray-900">Separate timing model · assumed elapsed hours from first signal</p>
        <BarChart className="mt-2 h-64" data={timing} index="metric" categories={["Assumed baseline", "Assumed assistance"]} colors={["gray", "emerald"]} valueFormatter={value => `${value.toFixed(1)} h`} yAxisWidth={44} />
        <p className="mt-2 text-xs text-gray-500">{projection.assumptions} These are model inputs, not observed benchmark runtimes, labor hours, or results from human investigators.</p>
      </div>
    </div>
  </Card>;
}
