const rows: { criterion: string; a: string; b: string; c: string; best?: "a" | "b" | "c" }[] = [
  {
    criterion: "What looks familiar",
    a: "A work queue with a detail pane, like TrackWise or Outlook. The finding is one more row.",
    b: "A batch record with tabs (Summary, Trends, Lab results, Events, Investigation), like an MES. A trend viewer with a pen list.",
    c: "Their own historian and QMS, unchanged. The Assistant is a small panel beside them.",
    best: "c",
  },
  {
    criterion: "Understand what needs attention",
    a: "First row of the queue, marked High and New, with the summary open beside it.",
    b: "Status pill in the batch header and the Assistant's first message.",
    c: "A button in the corner of the trend. Easy to miss.",
    best: "a",
  },
  {
    criterion: "Interactions to a source record",
    a: "1 · Select an evidence line in the detail pane.",
    b: "2 · Investigation tab, then an evidence row.",
    c: "3 · Open the Assistant, Evidence tab, then an item.",
    best: "a",
  },
  {
    criterion: "Understand findings and uncertainty",
    a: "Summary, three figures, titer chart and evidence list. Short.",
    b: "Every view an engineer already uses, plus the deviation drafted section by section with evidence, causes, checks and gaps.",
    c: "A short summary; the full record one click away.",
    best: "b",
  },
  {
    criterion: "Review the next action",
    a: "R from the queue item, then send.",
    b: "R from anywhere on the record, then send.",
    c: "Drafted straight into the QMS form; each field ticked, then saved with QMS's own button.",
    best: "c",
  },
  {
    criterion: "What is new to learn",
    a: "One line explains it: Assistant items in the queue, and drafts stay drafts.",
    b: "The Assistant panel, and Reviewed ticks on drafted sections.",
    c: "Almost nothing: one button in apps they already use.",
    best: "c",
  },
];

const label = { a: "A · Work queue", b: "B · Batch record", c: "C · Inside your apps" };

export default function Compare() {
  return (
    <main className="compare">
      <header className="compare-head">
        <h1>Three familiar places for the Assistant to work</h1>
        <p className="compare-lede">
          Each concept keeps a screen engineers already use (a work queue, a batch record, their own historian and QMS) and adds the Assistant inside it. Same scenario in all three: the Assistant notices the F-2408 titer shortfall, the engineer opens it, checks supporting and contradicting evidence, and reviews a verification plan. Interaction counts come from walking each prototype. Times were <b>not measured</b>.
        </p>
      </header>

      <div className="table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              <th scope="col">Criterion</th>
              {(["a", "b", "c"] as const).map((k) => (
                <th key={k} scope="col">
                  <a href={`?concept=${k}`}>{label[k]}</a>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.criterion}>
                <th scope="row">{r.criterion}</th>
                {(["a", "b", "c"] as const).map((k) => (
                  <td key={k} className={r.best === k ? "is-best" : ""}>
                    {r[k]}
                    {r.best === k && <span className="best-tag">Strongest</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="recommend">
        <h2>Recommendation: start inside their apps, give them a queue, keep the batch record for depth</h2>
        <div className="rec-grid">
          <div>
            <h3>Roll out C first</h3>
            <p>Nothing to learn and nothing to migrate: the Assistant appears beside the historian and drafts into the QMS they already use. It builds trust before anyone opens a new tool.</p>
          </div>
          <div>
            <h3>A becomes the daily start</h3>
            <p>A work queue is how engineers already plan a shift. Assistant findings and prepared records join it as rows, never as a separate inbox.</p>
          </div>
          <div>
            <h3>B is where they dig in</h3>
            <p>The batch record keeps the tabs and trend viewer they know, with the deviation drafted inside it. The Assistant panel answers by opening the right tab, so every answer is something they can check.</p>
          </div>
        </div>
        <h3 className="rec-sub">Rules that keep it familiar</h3>
        <ul className="rec-list">
          <li>
            <b>Their words, not ours:</b> Work queue, Batch record, Pens, Lab results, Events and alarms, Deviation.
          </li>
          <li>
            <b>One name and one symbol</b> for everything the Assistant did, and the word Draft until a person acts.
          </li>
          <li>
            <b>Every claim points to its record</b> in the system it came from, with Open in LIMS, MES or Historian.
          </li>
          <li>
            <b>Nothing is submitted by the Assistant.</b> People save with the same buttons they use today.
          </li>
        </ul>
        <h3 className="rec-sub">Before building further</h3>
        <p className="rec-p">Test with 6–8 process and QA engineers on their real tasks: find what needs attention, check a contradicting source, explain the missing data, review the plan, and get back to what they were doing. Measure time, errors and how often they say "where is that from?".</p>
      </section>
    </main>
  );
}
