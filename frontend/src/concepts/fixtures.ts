export const batches = [
  { hour: 0, product: 0.12, reference: 0.12, oxygen: 61, refOxygen: 60 },
  { hour: 8, product: 0.29, reference: 0.3, oxygen: 54, refOxygen: 55 },
  { hour: 16, product: 0.59, reference: 0.6, oxygen: 48, refOxygen: 49 },
  { hour: 24, product: 0.91, reference: 0.96, oxygen: 41, refOxygen: 44 },
  { hour: 32, product: 1.17, reference: 1.35, oxygen: 32, refOxygen: 41 },
  { hour: 40, product: 1.48, reference: 1.76, oxygen: 27, refOxygen: 40 },
  { hour: 48, product: 1.74, reference: 2.12, oxygen: 25, refOxygen: 40 },
];
export const evidence = [
  {
    id: "E01",
    kind: "support",
    title: "Product concentration is 18% below the reference mean",
    detail:
      "At 48 h, F-2408 is 1.74 g/L versus 2.12 g/L across six prior batches. This is a descriptive comparison; final yield is not yet available.",
    source: "LIMS · Assay P-1842",
    location: "Result 7 · 48 h sample",
    records: [
      ["F-2408", "48 h", "1.74 g/L"],
      ["Reference mean (n=6)", "48 h", "2.12 g/L"],
    ],
    caveat:
      "Reference batches share recipe R7 and vessel BR-04. Raw-material lot and inoculum differences remain unadjusted.",
  },
  {
    id: "E02",
    kind: "support",
    title: "Dissolved oxygen diverges after 24 hours",
    detail:
      "The historian shows 25% air saturation at 48 h, compared with a 40% reference mean. The timing overlaps the concentration change.",
    source: "Historian · BR04.DO.PV",
    location: "24–48 h · 1 min source cadence",
    records: [
      ["F-2408", "48 h", "25% air sat."],
      ["Reference mean (n=6)", "48 h", "40% air sat."],
    ],
    caveat:
      "Temporal association does not establish oxygen limitation. Independent probe confirmation and actual airflow are needed.",
  },
  {
    id: "E03",
    kind: "against",
    title: "Temperature and pH remain near their recipe targets",
    detail:
      "Temperature is 25.0 °C and pH is 6.5 at 48 h. These channels do not support a broad control failure.",
    source: "Historian · BR04.TEMP / PH",
    location: "48 h aligned observation",
    records: [
      ["Temperature", "48 h", "25.0 °C"],
      ["pH", "48 h", "6.5"],
    ],
    caveat:
      "Normal temperature and pH do not exclude an oxygen-transfer problem or another biological explanation.",
  },
  {
    id: "E04",
    kind: "against",
    title: "The oxygen probe calibration is in date",
    detail:
      "The maintenance record shows a passing calibration three days before batch start. Sensor error is less supported, but not ruled out.",
    source: "MES · Calibration CAL-082",
    location: "Maintenance record · revision 2",
    records: [
      ["Calibration result", "Pre-batch", "Pass"],
      ["Age at batch start", "—", "3 days"],
    ],
    caveat:
      "A prior calibration cannot establish current in-process sensor accuracy.",
  },
  {
    id: "E05",
    kind: "missing",
    title: "72-hour assay and actual airflow are unavailable",
    detail:
      "The next assay has not been posted. The airflow tag is outside this connector’s authorized scope. Neither value is inferred.",
    source: "LIMS / Historian · Data availability",
    location: "As of 09:42 · illustrative snapshot",
    records: [
      ["72 h product assay", "LIMS", "Not posted"],
      ["BR04.AIRFLOW.PV", "Historian", "Not authorized"],
    ],
    caveat:
      "Request the assay through the existing lab workflow and ask the connector administrator for scoped airflow access. Final yield and root cause remain unresolved.",
  },
] as const;
export type Evidence = (typeof evidence)[number];
