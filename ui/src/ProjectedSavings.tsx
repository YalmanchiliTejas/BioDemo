import { useState } from "react";
import { BarChart, Card, Text, Title } from "@tremor/react";

type Row = { metric: string; Today: number; "With agent": number };
type Props = { projection: { hours: Row[]; assumptions: string } };

const h = (v: number) => (v >= 10 ? `${Math.round(v)} h` : `${v.toFixed(1)} h`);
const usd = (v: number) => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3).toLocaleString()}k`);

// Published industry figures used by the plant calculator.
const INDUSTRY = {
  deviationsPerSite: 1500,      // BioPhorum (BPOG) survey of 13 companies
  minorShare: 0.72,             // BPOG: 72% minor, 28% major/critical
  minorHours: 18.1,             // BPOG: active hours per minor deviation
  minorOpsHours: 5.3,           // BPOG: of which operations staff (not making product)
  majorLaborUsd: 14000,         // Climet QM survey: labor cost per failure investigation, 2023
  repeatShare: 0.24,            // BPOG: share of deviations that are repeats
};
const SCENARIOS = [
  { id: "conservative", label: "Conservative", share: 0.2, basis: "Agent only removes evidence assembly: 5–7 of a 35-day investigation window (The FDA Group)." },
  { id: "midpoint", label: "Midpoint", share: 0.4, basis: "Halfway between evidence assembly only and the Lotic workflow model." },
  { id: "model", label: "Lotic model", share: 0.59, basis: "Engineer-hour reduction assumed in the Lotic workflow simulation." },
] as const;
const SOURCES = [
  ["BioPhorum Operations Group, “Transforming Deviation Management” (BioProcess International, 2017)", "https://www.bioprocessintl.com/risk-management/transforming-deviation-management",
    "~1,500 deviations per site per year; 72% minor; ~18.1 active hours per minor deviation (5.3 h operations); ~29 calendar days to close; majors 50–60 days; 24% repeats."],
  ["Climet Instruments survey of pharma Quality Managers (as summarized by Clinplex, 2026)", "https://clinplex.com/resources/deviation-investigation-cost-capa-closure-benchmarks",
    "Labor cost per failure investigation ≈ $14,000 in 2023, up from $10,000 in 2018. All-in deviation cost estimates reach ~$100,000."],
  ["The FDA Group, “A Model for Deviation Management: Lessons From the Field”", "https://www.thefdagroup.com/blog/deviation-management-model",
    "5–7 days of a 35-day timeline go to assembling batch records, photos, statements and logs before any real investigation starts."],
  ["Practitioner threads on Reddit (r/biotech, r/PharmaEire, r/pharmaindustry)", "https://www.reddit.com/r/biotech/comments/1piio9d/deviations_whats_the_most_frustrating_part_of",
    "Investigators call the process tedious and deadline-driven, with time going to tracking down records. Used for context only; no numbers are taken from Reddit."],
] as const;

export default function ProjectedSavings({ projection }: Props) {
  const [deviations, setDeviations] = useState(INDUSTRY.deviationsPerSite);
  const [rate, setRate] = useState(120);
  const [scenarioId, setScenarioId] = useState<(typeof SCENARIOS)[number]["id"]>("conservative");
  const scenario = SCENARIOS.find(s => s.id === scenarioId)!;
  const timing = projection.hours.filter(r => !r.metric.startsWith("Engineer"));

  const minor = deviations * INDUSTRY.minorShare, major = deviations - minor;
  const minorHoursToday = minor * INDUSTRY.minorHours;
  const majorHoursToday = (major * INDUSTRY.majorLaborUsd) / rate;
  const costToday = minorHoursToday * rate + major * INDUSTRY.majorLaborUsd;
  const hoursSaved = (minorHoursToday + majorHoursToday) * scenario.share;
  const costSaved = costToday * scenario.share;
  const opsHoursBack = minor * INDUSTRY.minorOpsHours * scenario.share;
  const fte = hoursSaved / 1800;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Title>Projected hours and budget saved</Title>
          <Text>Based on published deviation-management benchmarks for pharma and biotech plants. Adjust them to match your site.</Text>
        </div>
        <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">Projected</span>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Investigation spend today", usd(costToday), `${Math.round(minor).toLocaleString()} minor × ${INDUSTRY.minorHours} h + ${Math.round(major).toLocaleString()} major × $14k`],
          ["Projected budget saved / year", usd(costSaved), `${Math.round(scenario.share * 100)}% of investigation labor`],
          ["Engineer & QA hours saved / year", Math.round(hoursSaved).toLocaleString(), `≈ ${fte.toFixed(1)} full-time people freed up`],
          ["Operator hours back on the floor", Math.round(opsHoursBack).toLocaleString(), "per year, from minor deviations alone"],
        ].map(([label, value, note], i) => (
          <div key={label} className={`rounded-lg border p-4 ${i === 0 ? "border-gray-200" : "border-emerald-200 bg-emerald-50/40"}`}>
            <p className="text-sm font-medium text-gray-900">{label}</p>
            <p className={`mt-1 text-2xl font-semibold ${i === 0 ? "text-gray-700" : "text-emerald-700"}`}>{value}</p>
            <p className="mt-1 text-xs text-gray-500">{note}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <div className="rounded-lg border border-gray-200 p-5 lg:col-span-2">
          <p className="text-sm font-semibold text-gray-900">Your plant</p>
          <label className="mt-4 block text-xs text-gray-600">Deviations per year: <b className="text-gray-900">{deviations.toLocaleString()}</b>
            <span className="text-gray-400"> (industry average ≈ 1,500 per site)</span>
            <input type="range" min={50} max={3000} step={50} value={deviations} onChange={e => setDeviations(Number(e.target.value))} className="mt-1 w-full accent-emerald-600" />
          </label>
          <label className="mt-3 block text-xs text-gray-600">Loaded engineer / QA cost per hour: <b className="text-gray-900">${rate}</b>
            <input type="range" min={60} max={250} step={5} value={rate} onChange={e => setRate(Number(e.target.value))} className="mt-1 w-full accent-emerald-600" />
          </label>
          <p className="mt-4 text-xs text-gray-600">How much of the investigation work the agent takes over:</p>
          <div className="mt-2 grid grid-cols-3 gap-1 rounded-lg bg-gray-100 p-1">
            {SCENARIOS.map(s => (
              <button key={s.id} onClick={() => setScenarioId(s.id)}
                className={`rounded-md px-2 py-1.5 text-xs font-medium ${s.id === scenarioId ? "bg-white text-emerald-700 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
                {s.label} · {Math.round(s.share * 100)}%
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-500">{scenario.basis}</p>
          <p className="mt-4 text-xs text-gray-500">Not counted: the {Math.round(INDUSTRY.repeatShare * 100)}% of deviations that are repeats, batch holds, or lost batches ($250k–$500k each), all of which the cross-batch linking in the Fresenius replay targets.</p>
        </div>
        <div className="lg:col-span-3">
          <p className="text-sm font-medium text-gray-900">Hours from first signal, per deviation (Lotic workflow model)</p>
          <BarChart className="mt-2 h-64" data={timing} index="metric" categories={["Today", "With agent"]} colors={["gray", "emerald"]}
            valueFormatter={h} yAxisWidth={44} />
          <p className="mt-2 text-xs text-gray-400">{projection.assumptions} The model's 16.6 engineer hours per deviation today is close to BioPhorum's 18.1 hours for a minor deviation.</p>
        </div>
      </div>

      <details className="mt-5 rounded-lg bg-gray-50 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-gray-900">Where these numbers come from</summary>
        <ul className="mt-3 space-y-3">
          {SOURCES.map(([title, url, text]) => (
            <li key={url} className="text-sm">
              <a href={url} target="_blank" rel="noreferrer" className="font-medium text-emerald-700 underline">{title}</a>
              <p className="text-xs text-gray-600">{text}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-gray-500">These are projections built from industry averages and assumed agent coverage, not measured savings from Lotic deployments. A shadow pilot on your own deviations would replace them with measured figures.</p>
      </details>
    </Card>
  );
}
