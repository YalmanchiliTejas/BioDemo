import { useEffect, useRef, useState } from "react";
import { RiArrowRightLine, RiCheckLine } from "@remixicon/react";
import "@fontsource-variable/manrope";
import "./landing.css";

const apps = [
  { id: "historian", name: "Historian", product: "PlantView", note: "BR-04 agitation has been at its 800 rpm limit since 27 h. DO left its setpoint the same hour." },
  { id: "lims", name: "LIMS", product: "LabWare", note: "The 36 h and 48 h titer results are below the range of the last six R7 batches." },
  { id: "mes", name: "MES", product: "Syncade", note: "Step 4.3 records a foam alarm at 22 h. Antifoam use rose after it." },
  { id: "qms", name: "QMS", product: "QualityTrack", note: "A deviation is drafted with three verification tasks. It waits for your check before it is saved." },
] as const;

const useReveal = () => {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            io.unobserve(e.target);
          }
        }),
      { rootMargin: "0px 0px -12% 0px" },
    );
    root.querySelectorAll(".reveal").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return ref;
};

export default function Landing() {
  const [app, setApp] = useState<(typeof apps)[number]["id"]>("historian");
  const ref = useReveal();
  const current = apps.find((a) => a.id === app)!;

  useEffect(() => {
    document.title = "Manufacturing OS · Investigate with evidence";
    document.documentElement.classList.add("js");
  }, []);

  return (
    <main className="lp" ref={ref}>
      <header className="lp-nav">
        <a className="lp-word" href="/">
          Manufacturing OS
        </a>
        <nav aria-label="Page">
          <a href="#how">How it works</a>
          <a href="#trust">Review principles</a>
        </nav>
        <a className="lp-btn lp-btn-light lp-nav-cta" href="/app">
          Open the workspace
        </a>
      </header>

      <section className="lp-hero" aria-labelledby="hero-h">
        <div className="lp-hero-text">
          <p className="lp-eyebrow">Manufacturing investigations</p>
          <h1 id="hero-h">Make sense of<br />the batch.</h1>
          <p className="lp-sub">Move forward with evidence.</p>
          <p className="lp-lede">Review process trends, lab results and batch records in one workspace. See what changed, inspect the evidence, and review the proposed next step.</p>
          <div className="lp-actions">
            <a className="lp-btn lp-btn-light" href="/app">
              Open the workspace <RiArrowRightLine size={18} />
            </a>
            <a className="lp-link-light" href="#how">
              See how it works
            </a>
          </div>
          <p className="lp-demo-note">Interactive demo · simulated plant data</p>
        </div>
        <figure className="lp-hero-pic">
          <img src="/os/assets/bioreactor-in-operation.jpg" alt="A stainless-steel bioreactor with its control panel and piping in a clean room" width={1920} height={1440} />
          <figcaption>A pilot-scale bioreactor. The kind of vessel the Assistant watches through your historian.</figcaption>
        </figure>
      </section>

      <section className="lp-sec lp-apps" id="how" aria-labelledby="apps-h">
        <div className="lp-side">
          <h2 id="apps-h">Keep the source<br />in view.</h2>
          <p className="reveal">Follow the sample batch across process trends, laboratory results, batch records and quality review. Each view adds context to the same investigation.</p>
        </div>
        <div className="lp-live reveal" data-ui>
          <div className="lp-tabs" role="tablist" aria-label="Choose an application">
            {apps.map((a, index) => (
              <button key={a.id} id={`preview-tab-${a.id}`} type="button" role="tab" aria-selected={app === a.id} aria-controls="application-preview" tabIndex={app === a.id ? 0 : -1} onClick={() => setApp(a.id)} onKeyDown={(event) => {
                const next = event.key === "ArrowRight" ? (index + 1) % apps.length : event.key === "ArrowLeft" ? (index + apps.length - 1) % apps.length : event.key === "Home" ? 0 : event.key === "End" ? apps.length - 1 : null;
                if (next !== null) { event.preventDefault(); setApp(apps[next].id); document.getElementById(`preview-tab-${apps[next].id}`)?.focus(); }
              }}>
                {a.name}
                <small>{a.product}</small>
              </button>
            ))}
          </div>
          <div className="lp-live-body" id="application-preview" role="tabpanel" aria-labelledby={`preview-tab-${app}`} aria-live="polite" tabIndex={0}>
            <p className="lp-live-who">The Assistant, beside {current.product} {current.name}</p>
            <p className="lp-live-note">{current.note}</p>
            <p className="lp-live-src">Batch F-2408 · BR-04 · simulated example</p>
          </div>
        </div>
      </section>

      <section className="lp-sec lp-steps" aria-labelledby="steps-h">
        <figure className="lp-pic-tall reveal">
          <img src="/os/assets/btec-bioreactors.jpg" alt="Two stainless-steel bioreactors with control cabinets and sample vessels in a process development lab" width={1000} height={750} loading="lazy" />
        </figure>
        <div>
          <h2 id="steps-h">From a finding<br />to a reviewed next step.</h2>
          <ol className="lp-ol">
            <li className="reveal">
              <b>It notices.</b> Titer on batch F-2408 falls 18 % below the reference range at 48 h. The finding lands in your work queue like any other item.
            </li>
            <li className="reveal">
              <b>It shows its evidence.</b> Three records support the leading explanation, two contradict it, three are missing. Each links to the record in its own system.
            </li>
            <li className="reveal">
              <b>It drafts, you decide.</b> The deviation arrives pre-filled in your QMS. You tick each section and save it with the QMS's own button.
            </li>
          </ol>
        </div>
      </section>

      <section className="lp-sec lp-trust" id="trust" aria-labelledby="trust-h">
        <h2 id="trust-h">Evidence you can inspect.<br />Decisions you control.</h2>
        <div className="lp-trust-grid">
          <div className="reveal">
            <h3>Read only</h3>
            <p>Connectors read your systems inside a scope your administrator sets. The only write is a QMS draft, and a person saves it.</p>
          </div>
          <div className="reveal">
            <h3>Every claim cited</h3>
            <p>Each statement points to a historian tag, a LIMS sample or an MES step, with the query that fetched it.</p>
          </div>
          <div className="reveal">
            <h3>Gaps shown as gaps</h3>
            <p>Missing data is drawn as missing, never filled in. Confidence is a word with reasons, never a made-up percentage.</p>
          </div>
        </div>
        <figure className="lp-wide reveal">
          <img src="/os/assets/bioreactor-1.jpg" alt="A glass bench-top bioreactor with tubing beside a stainless vessel on a laboratory bench" width={1920} height={1440} loading="lazy" />
        </figure>
      </section>

      <section className="lp-sec lp-start" id="start" aria-labelledby="start-h">
        <div>
          <h2 id="start-h">A clearer place to start.</h2>
          <ul className="lp-checks">
            <li className="reveal">
              <RiCheckLine size={20} /> See the batch findings that need your attention
            </li>
            <li className="reveal">
              <RiCheckLine size={20} /> Follow every finding back to its source records
            </li>
            <li className="reveal">
              <RiCheckLine size={20} /> Review proposed actions before saving a draft
            </li>
            <li className="reveal">
              <RiCheckLine size={20} /> Runs on your existing Prime Agent and FastAPI services
            </li>
          </ul>
        </div>
        <figure className="lp-pic-square reveal">
          <img src="/os/assets/bioreactor-akureyri.jpg" alt="Serum bottles of culture medium with syringes ready for sampling" width={1500} height={2000} loading="lazy" />
        </figure>
      </section>

      <footer className="lp-foot" aria-labelledby="foot-h">
        <h2 id="foot-h">Try the investigation.</h2>
        <div className="lp-foot-grid">
          <div>
            <h3>Start with batch F-2408</h3>
            <p>Explore the finding, compare the evidence and review the proposed quality action.</p>
            <a className="lp-btn lp-btn-light" href="/app">
              Open workspace <RiArrowRightLine size={18} />
            </a>
          </div>
          <div>
            <h3>Try the workspace</h3>
            <p>A working prototype with simulated plant data.</p>
            <a className="lp-link-light" href="/app">
              Open the workspace
            </a>
          </div>
        </div>
        <p className="lp-credits">
          Pictures: <a href="https://commons.wikimedia.org/wiki/File:Bioreactor_in_operation.jpg">“Bioreactor in operation”</a> by Habin Zhang, <a href="https://creativecommons.org/licenses/by-sa/4.0">CC BY-SA 4.0</a>; <a href="https://commons.wikimedia.org/wiki/File:BTEC_Bioreactors.jpg">“BTEC Bioreactors”</a> by RickLawless, <a href="https://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>; <a href="https://commons.wikimedia.org/wiki/File:Bioreactor_1.jpg">“Bioreactor 1”</a> by Luis Fernando Flores LAB, <a href="https://creativecommons.org/licenses/by-sa/4.0">CC BY-SA 4.0</a>; <a href="https://commons.wikimedia.org/wiki/File:Bioreactor_Akureyri.jpg">“Bioreactor Akureyri”</a> by Fribbi, public domain. All via Wikimedia Commons. Plant data on this page is simulated.
        </p>
      </footer>
    </main>
  );
}
