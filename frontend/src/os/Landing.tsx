import { useEffect, useRef, useState } from "react";
import {
  RiArrowRightLine,
  RiDatabase2Line,
  RiFileList3Line,
  RiFlaskLine,
  RiLineChartLine,
  RiShieldCheckLine,
  RiStackLine,
  RiUserLine,
} from "@remixicon/react";
import "@fontsource-variable/manrope";
import "@fontsource/ibm-plex-mono/400.css";
import "./landing.css";
import {
  Atmosphere,
  MotionControl,
  MotionProvider,
  useAmbientMotion,
} from "./Atmosphere";
import { GoalComposer } from "./GoalComposer";
import { WorkflowGallery } from "./WorkflowGallery";
import { carryEntry, emptyEntry, type WorkEntry } from "./work-entry";

const systems = [
  {
    id: "historian",
    name: "Historian",
    product: "PlantView",
    icon: RiLineChartLine,
    kind: "Process observation",
    note: "BR-04 agitation has been at its 800 rpm limit since 27 h. DO left its setpoint the same hour.",
    limit: "The signals coincide. They do not establish the cause.",
  },
  {
    id: "lims",
    name: "LIMS",
    product: "LabWare",
    icon: RiFlaskLine,
    kind: "Laboratory result",
    note: "The 36 h and 48 h titer results are below the range of the last six R7 batches.",
    limit: "The reference is descriptive. The 60 h assay is still pending.",
  },
  {
    id: "mes",
    name: "MES",
    product: "Syncade",
    icon: RiFileList3Line,
    kind: "Recorded event",
    note: "Step 4.3 records a foam alarm at 22 h. Antifoam use rose after it.",
    limit:
      "A sequence of events is evidence to examine, not a confirmed causal link.",
  },
  {
    id: "qms",
    name: "QMS",
    product: "QualityTrack",
    icon: RiShieldCheckLine,
    kind: "Proposed next step",
    note: "A verification plan links three checks to the sample evidence. A person reviews it before any handoff.",
    limit:
      "The demo saves a simulated draft locally. It does not update a live QMS.",
  },
] as const;

const thread = [
  {
    index: "01",
    label: "Observe",
    title: "The result moved.",
    body: "The 48 h titer is 1.74 g/L, 18% below the six-batch R7 reference. The chart keeps the reference range visible.",
    meta: "LIMS · F-2408 · 48 h",
  },
  {
    index: "02",
    label: "Interpret",
    title: "Two explanations stay open.",
    body: "Reduced oxygen transfer is one explanation. F-2391 held low DO and finished normally, so it is not enough on its own.",
    meta: "3 support · 2 contradict · 3 missing",
  },
  {
    index: "03",
    label: "Act",
    title: "A next step you can review.",
    body: "Verify DO at the 12:00 sample, recover the missing off-gas records, and route the proposal to QA. Nothing is executed here.",
    meta: "Owner: process engineer · Review: QA",
  },
] as const;

const architecture = [
  {
    step: "01",
    icon: RiDatabase2Line,
    title: "Systems of record",
    label: "Read-only samples",
    body: "MES, LIMS, historian and QMS remain authoritative. The demo reads labeled snapshots and writes nothing back.",
    meta: "MES · LIMS · Historian · QMS",
  },
  {
    step: "02",
    icon: RiStackLine,
    title: "Workspace",
    label: "The demo surface",
    body: "One work model keeps the question, evidence, calculations and proposed next step together in this browser.",
    meta: "Work model · provenance · local storage",
  },
  {
    step: "03",
    icon: RiUserLine,
    title: "People",
    label: "Authority stays human",
    body: "A person inspects the evidence, corrects the record and decides whether a next step is ready for review.",
    meta: "Inspect · correct · review",
  },
] as const;

export default function Landing() {
  return (
    <MotionProvider>
      <LandingPage />
    </MotionProvider>
  );
}

function LandingPage() {
  const { paused, reduced } = useAmbientMotion();
  const root = useRef<HTMLElement>(null);
  const [entry, setEntry] = useState<WorkEntry>(emptyEntry);
  const [handoffError, setHandoffError] = useState("");
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    document.title =
      "Manufacturing OS · Start with what changed.";
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.08 },
    );
    root.current
      ?.querySelectorAll(".reveal")
      .forEach((el) => observer.observe(el));
    if (root.current) root.current.dataset.motionReady = "true";
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const steps = root.current?.querySelectorAll<HTMLElement>(".lp-arch-step");
    if (!steps?.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        const index = Number((visible.target as HTMLElement).dataset.step);
        if (!Number.isNaN(index)) setActiveStep(index);
      },
      { rootMargin: "-35% 0px -35% 0px", threshold: [0, 0.2, 0.5, 1] },
    );
    steps.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const archState = (index: number) =>
    activeStep === index ? "active" : activeStep > index ? "done" : "next";

  const chooseEntry = (draft: WorkEntry) => {
    setEntry(draft);
    setHandoffError("");
    document.getElementById("hero-h")?.scrollIntoView({
      block: "start",
      behavior: paused || reduced ? "auto" : "smooth",
    });
    document.getElementById("landing-goal")?.focus({ preventScroll: true });
  };

  const openEntry = () => {
    try {
      location.assign(carryEntry(entry));
    } catch {
      setHandoffError(
        "This browser could not carry your draft to the workspace. Your text is still here; copy it before continuing.",
      );
    }
  };

  return (
    <main
      className="lp"
      ref={root}
      data-motion={paused || reduced ? "still" : "full"}
    >
      <a className="lp-skip" href="#thread">
        Skip to the work
      </a>

      <header className="lp-nav">
        <a className="lp-word" href="/">
          Manufacturing<span>OS</span>
        </a>
        <nav aria-label="Page">
          <a href="#thread">The work</a>
          <a href="#architecture">Architecture</a>
          <a href="#start">Starting points</a>
          <a href="#systems">Systems</a>
        </nav>
        <a className="lp-nav-link" href="/app">
          Demo workspace <RiArrowRightLine size={15} aria-hidden="true" />
        </a>
      </header>

      <section className="lp-hero" aria-labelledby="hero-h">
        <div className="lp-hero-bg" aria-hidden="true">
          <Atmosphere className="lp-hero-atmosphere" priority />
          <div className="lp-hero-veil" />
          <div className="lp-hero-grid" />
          <div className="lp-hero-scan" />
        </div>

        <div className="lp-hero-inner">
          <div className="lp-hero-copy">
            <p className="lp-kicker">Manufacturing intelligence</p>
            <h1 id="hero-h">
              Start with
              <br />
              <span>what changed.</span>
            </h1>
            <p className="lp-lede">
              Ask a question, follow the evidence, and leave with a next step.
            </p>
            <GoalComposer
              id="landing-goal"
              value={entry}
              onChange={(value) => {
                setEntry(value);
                setHandoffError("");
              }}
              onSubmit={openEntry}
              submitLabel="Open in workspace"
              dark
            />
            {handoffError && (
              <div className="lp-handoff-error" role="alert">
                <p>{handoffError}</p>
                <a href="/app">Open the workspace directly →</a>
              </div>
            )}
            <div className="lp-hero-foot">
              <p>Interactive sample · No live systems connected</p>
              <MotionControl />
            </div>
          </div>

          <aside className="lp-hero-sample" aria-label="Sample thread summary">
            <div className="lp-hero-sample-head">
              <span>Sample thread</span>
              <span>F-2408 · BR-04</span>
            </div>
            <div className="lp-hero-sample-result">
              <span>48 h titer</span>
              <strong>
                1.74 <small>g/L</small>
              </strong>
              <em>−18% vs reference</em>
            </div>
            <div className="lp-hero-sample-chart" aria-hidden="true">
              <svg viewBox="0 0 320 52" preserveAspectRatio="none">
                <rect
                  className="lp-hero-chart-band"
                  x="0"
                  y="10"
                  width="320"
                  height="16"
                />
                <path className="lp-hero-chart-ref" d="M0 24H320" />
                <path
                  className="lp-hero-chart-line"
                  d="M0 15C32 14 60 16 92 19S156 27 198 33 268 44 320 47"
                />
                <circle className="lp-hero-chart-dot" cx="320" cy="47" r="3" />
              </svg>
              <span>48 h</span>
            </div>
            <ol className="lp-hero-sample-nodes">
              <li>
                <span>27 h</span>
                <p>DO leaves setpoint</p>
              </li>
              <li>
                <span>48 h</span>
                <p>Titer below reference</p>
              </li>
              <li>
                <span>Next</span>
                <p>Verify DO; recover off-gas</p>
              </li>
            </ol>
            <div className="lp-hero-sample-foot">
              <span>R7 reference · six batches</span>
              <a href="/app?view=item&work=sample-f2408">
                Open the sample thread
                <RiArrowRightLine size={13} aria-hidden="true" />
              </a>
            </div>
          </aside>
        </div>

        <div className="lp-hero-status">
          <span>
            <i /> Sample mode
          </span>
          <span>Read-only snapshots</span>
          <span>Browser-local workspace</span>
          <span>Human review</span>
          <span className="lp-hero-status-ref">F-2408 · R7 reference</span>
        </div>
      </section>

      <section className="lp-principles" aria-label="How the workspace behaves">
        <p>
          <span>Read-only by default</span>
          <span>Source kept with every claim</span>
          <span>Human review stays explicit</span>
        </p>
      </section>

      <section
        className="lp-thread lp-section"
        id="thread"
        aria-labelledby="thread-h"
      >
        <div className="lp-section-head reveal">
          <h2 id="thread-h">Follow one question through.</h2>
          <p>
            The question, the evidence, and the next step stay in one place.
          </p>
        </div>
        <div className="lp-thread-grid reveal">
          {thread.map((step) => (
            <article className="lp-thread-card" key={step.index}>
              <span className="lp-thread-index" aria-hidden="true">
                {step.index}
              </span>
              <p className="lp-thread-label">{step.label}</p>
              <h3>{step.title}</h3>
              <p className="lp-thread-body">{step.body}</p>
              <p className="lp-thread-meta">{step.meta}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="lp-arch" id="architecture" aria-labelledby="arch-h">
        <div className="lp-arch-field" aria-hidden="true" />
        <div className="lp-arch-inner">
          <div className="lp-arch-intro reveal">
            <div>
              <p className="lp-arch-kicker">
                Architecture · reference, not a deployment claim
              </p>
              <h2 id="arch-h">A thin layer over the systems you already trust.</h2>
            </div>
            <div className="lp-arch-intro-side">
              <p className="lp-arch-lede">
                The demo keeps one work surface in the browser and reads labeled
                snapshots from the systems that remain the record. No live write
                path is configured.
              </p>
              <a className="lp-arch-link" href="/app?view=sources">
                Inspect the sample source boundary
                <RiArrowRightLine size={15} aria-hidden="true" />
              </a>
            </div>
          </div>

          <div className="lp-arch-stage">
            <div className="lp-arch-steps">
              {architecture.map((node, index) => (
                <article
                  className="lp-arch-step reveal"
                  data-step={index}
                  data-active={activeStep === index}
                  key={node.step}
                >
                  <div className="lp-arch-step-top">
                    <span className="lp-arch-step-number">{node.step}</span>
                    <span className="lp-arch-icon" aria-hidden="true">
                      <node.icon size={18} />
                    </span>
                  </div>
                  <p className="lp-arch-label">{node.label}</p>
                  <h3>{node.title}</h3>
                  <p className="lp-arch-body">{node.body}</p>
                  <p className="lp-arch-meta">{node.meta}</p>
                </article>
              ))}
            </div>

            <div className="lp-arch-map-column">
              <div className="lp-arch-plate reveal" aria-hidden="true">
                <div className="lp-arch-plate-head">
                  <div>
                    <p className="lp-arch-plate-kicker">Reference architecture</p>
                    <p className="lp-arch-plate-title">
                      One work surface. No new system of record.
                    </p>
                  </div>
                  <span className="lp-arch-mode">
                    <i /> Sample mode
                  </span>
                </div>

                <div className="lp-arch-map">
                  <div
                    className="lp-arch-layer lp-arch-sources"
                    data-state={archState(0)}
                  >
                    <div className="lp-arch-layer-head">
                      <span>01</span>
                      <b>Systems of record</b>
                    </div>
                    <ul className="lp-arch-chips">
                      {systems.map((system) => (
                        <li key={system.id}>
                          <system.icon size={13} aria-hidden="true" />
                          <span>{system.name}</span>
                          <small>{system.product}</small>
                        </li>
                      ))}
                    </ul>
                    <p className="lp-arch-layer-note">Read-only snapshots</p>
                  </div>

                  <div className="lp-arch-flow" data-state={archState(0)}>
                    <span className="lp-arch-flow-line" />
                    <span className="lp-arch-flow-packet" />
                    <span className="lp-arch-flow-label">read</span>
                  </div>

                  <div
                    className="lp-arch-layer lp-arch-workspace"
                    data-state={archState(1)}
                  >
                    <div className="lp-arch-layer-head">
                      <span>02</span>
                      <b>Browser-local workspace</b>
                    </div>
                    <div className="lp-arch-work">
                      <div className="lp-arch-work-head">
                        <span>F-2408</span>
                        <em>BR-04 · 48 h</em>
                      </div>
                      <div className="lp-arch-work-chart">
                        <svg viewBox="0 0 220 36" preserveAspectRatio="none">
                          <path className="lp-arch-chart-ref" d="M0 14H220" />
                          <path
                            className="lp-arch-chart-line"
                            d="M0 8C20 7 38 9 60 12S104 19 132 23 180 31 220 33"
                          />
                          <circle
                            className="lp-arch-chart-dot"
                            cx="220"
                            cy="33"
                            r="2.5"
                          />
                        </svg>
                      </div>
                      <ul className="lp-arch-work-rows">
                        <li>
                          <span>Question</span>
                          <b>Why did titer move?</b>
                        </li>
                        <li>
                          <span>Evidence</span>
                          <b>4 sources · 2 open</b>
                        </li>
                        <li>
                          <span>Next</span>
                          <b>Verify DO; recover off-gas</b>
                        </li>
                      </ul>
                    </div>
                    <p className="lp-arch-layer-note">
                      Question · evidence · next step
                    </p>
                  </div>

                  <div className="lp-arch-flow" data-state={archState(1)}>
                    <span className="lp-arch-flow-line" />
                    <span className="lp-arch-flow-packet" />
                    <span className="lp-arch-flow-label">review</span>
                  </div>

                  <div
                    className="lp-arch-layer lp-arch-people"
                    data-state={archState(2)}
                  >
                    <div className="lp-arch-layer-head">
                      <span>03</span>
                      <b>People</b>
                    </div>
                    <div className="lp-arch-review">
                      <span className="lp-arch-avatar">JD</span>
                      <div>
                        <p>Reviewer</p>
                        <b>Inspects the evidence</b>
                      </div>
                    </div>
                    <ul className="lp-arch-decisions">
                      <li>
                        <span>✓</span> Correct the record
                      </li>
                      <li>
                        <span>→</span> Approve a next step
                      </li>
                      <li>
                        <span>×</span> Stop or revise
                      </li>
                    </ul>
                    <p className="lp-arch-layer-note">Authority stays human</p>
                  </div>
                </div>

                <div className="lp-arch-plate-foot">
                  <div className="lp-arch-progress" aria-hidden="true">
                    {architecture.map((node, index) => (
                      <span key={node.step} data-on={index <= activeStep} />
                    ))}
                  </div>
                  <p>No live write path configured</p>
                </div>
              </div>
              <div className="lp-arch-map-caption" aria-hidden="true">
                <span>Read-only snapshots → browser-local work → human review</span>
                <span>Scroll to follow the handoffs</span>
              </div>
            </div>
          </div>

          <div className="lp-arch-boundary reveal">
            <div className="lp-arch-boundary-head">
              <p className="lp-arch-kicker">Boundary</p>
              <h3>What is real here?</h3>
              <p>
                The sample is complete enough to inspect the interaction. It is
                not a claim about a production integration.
              </p>
            </div>
            <div className="lp-arch-boundary-grid">
              <div>
                <p className="lp-arch-status is-demo">In this demo</p>
                <ul>
                  <li>Sample records only</li>
                  <li>Browser-local persistence</li>
                  <li>Simulated QMS draft</li>
                </ul>
              </div>
              <div>
                <p className="lp-arch-status is-prod">In a real deployment</p>
                <ul>
                  <li>Authenticated, scoped connectors</li>
                  <li>Approved write paths and audit trail</li>
                  <li>Validation and permissions per site</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        className="lp-start lp-section"
        id="start"
        aria-labelledby="start-h"
      >
        <div className="lp-section-head reveal">
          <h2 id="start-h">What are you working on?</h2>
          <p>A question, a comparison, a check, or something new.</p>
        </div>
        <div className="reveal">
          <WorkflowGallery onChoose={chooseEntry} />
        </div>
      </section>

      <section
        className="lp-systems lp-section"
        id="systems"
        aria-labelledby="systems-h"
      >
        <div className="lp-section-head reveal">
          <h2 id="systems-h">Keep the systems your team already uses.</h2>
          <p>
            The workspace reads within a defined scope and leaves the record
            where it already lives.
          </p>
        </div>
        <div className="lp-systems-list reveal">
          {systems.map((system) => (
            <a
              className="lp-system"
              key={system.id}
              href={`/app?view=${system.id}`}
            >
              <span className="lp-system-icon" aria-hidden="true">
                <system.icon size={18} />
              </span>
              <span className="lp-system-name">
                <b>{system.product}</b>
                <small>
                  {system.name} · {system.kind}
                </small>
              </span>
              <span className="lp-system-note">{system.note}</span>
              <span className="lp-system-limit">{system.limit}</span>
              <RiArrowRightLine
                className="lp-system-arrow"
                size={16}
                aria-hidden="true"
              />
            </a>
          ))}
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-footer-top">
          <a className="lp-word" href="/">
            Manufacturing<span>OS</span>
          </a>
          <p>
            A browser-local demonstrator. Sample records only. No live MES,
            LIMS, historian, or QMS connection is configured.
          </p>
        </div>
        <div className="lp-footer-bottom">
          <nav aria-label="Footer">
            <a href="#thread">The work</a>
            <a href="#architecture">Architecture</a>
            <a href="#start">Starting points</a>
            <a href="#systems">Systems</a>
          </nav>
          <a href="#hero-h">Back to top ↑</a>
        </div>
      </footer>
    </main>
  );
}
