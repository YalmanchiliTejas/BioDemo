# New entrants marketing "AI agents" for pharma manufacturing, quality, CMC and validation: what ships as of 2026-11-16

**Reading notes.** **F** = page opened with WebFetch; **S** = seen only in a search-result summary. **VC** vendor claim, **VD** vendor documentation, **IE** independently evidenced. Quotes are passages the fetch tool returned in quotation marks, not re-checked against page source. "Undated" pages carry only a © 2026 footer. The shared web-search budget ran out part-way, so some follow-ups were not run (listed at the end). Nothing comes from memory.

## 1. Which entrants show agents that take multi-step actions across systems or run in the background, versus document Q&A or single-step drafting?

### Takeaway
Six entrants describe multi-step or background agent work in some detail (Seal, Katalyze, Mareana, Qualio, ComplianceQuest, xLM); the rest are drafting pipelines or in-form assistants. Every entrant that states a write model says the agent proposes and people approve. None documents an agent writing to an external system of record, and all capability evidence is vendor-authored.

### Cited Findings
**Multi-step, cross-system or background (as the vendor describes it)**
- **Seal** — legal entity "Opvia Ltd."; YC Summer 2020, founded 2019, London, team of 40 ([YC profile](https://www.ycombinator.com/companies/seal-2), undated, F, VC). Agent "Neil": "It reads your runs and records, then drafts the comparison, the gap assessment or the review"; jobs include "Draft a deviation investigation." and "Prepare batch B-2407 for review."; "All 52 jobs"; a save-time trigger: "Each result is read against its limits, controls and earlier runs as it's saved." ([seal.run/neil](https://seal.run/neil), undated, F, VC). It "reads your records where you keep them, from SAP to AVEVA PI, and drafts the paperwork. People decide." ([seal.run](https://seal.run/), undated, F, VC). No beta or GA label.
- **Katalyze AI** — $10.5M seed led by Bonfire Ventures; 40 staff; Toronto and San Francisco ([BetaKit](https://betakit.com/katalyze-ai-thinks-the-future-of-pharma-operations-is-teams-of-ai-agents/), 2026-07-06, F, IE). Founding year 2023 is S only. Four agentic solutions "Run today": Yield Optimization, Deviation Investigation, Raw Material Characterization, Tech Transfer. In the deviation example the agent queries four sources, reads 12 batch records, tests two hypotheses and drafts an investigation with "every line cited"; a human revises ([agentic solutions](https://www.katalyzeai.com/product/agentic-solutions), undated, F, VC). "Katalyst" launched 2026-01-20 as "an AI agent purpose-built for pharmaceutical manufacturing" with "always-on process monitoring"; GA or beta not stated ([press release](https://www.biopharmadive.com/press-release/20260120-katalyze-ai-launches-katalyst-ai-agent-for-pharmaceutical-manufacturing-1/), F, VC).
- **Mareana** — founding year and funding not stated; it cites a 2019 Gartner Cool Vendor listing, so it predates 2022 ([about](https://mareana.com/about-us/), undated, F, VC). "Mareana is the agentic platform for pharma manufacturing."; "all six modules are available today, EBR in beta." ([homepage](https://www.mareana.com/), undated, F, VC). Batch Review Copilot pulls from LIMS, ERP and scanned records via "AI-OCR", runs rules on "ranges, signatures, and calculations" plus anomaly detection, and shows reviewers only flagged items ([product page](https://mareana.com/batch-review-copilot/), undated, F, VC).
- **Qualio** — "Trusted by over 700 customers."; framework assessment "reruns whenever a record changes." ([homepage](https://www.qualio.com), undated, F, VC). Founder's post: "Agents that autonomously run impact assessments, perform gap analyses, collect evidence, generate corrective actions,"; yet "That is the company Qualio is building." ([blog](https://www.qualio.com/blog/the-agentic-compliance-era), 2026-08-25, F, VC). Qualio "announced general availability of Compliance Intelligence," ([MedTech Spectrum](https://medtechspectrum.com/news/16/24912/qualio-announces-compliance-intelligence-ai-powered-solution-advancing-life-sciences-grc-platform.html), 2025-10-15, F, VC rewrite).
- **ComplianceQuest** — the Salesforce alliance "formalizes the adoption of Agentforce as its core Agentic AI framework." ([release](https://www.newswire.com/news/compliancequest-and-salesforce-reaffirm-strategic-partnership-embraces-22650882), 2025-10-07, F, VC). Summer '26, "generally available on July 31, 2026.": "The enhanced CQ.AI Investigation Assistant analyzes historical investigation records and FMEA data"; "The new CQ.AI Safety Agent enabled employees to describe an incident in plain language." and pre-populates the incident record ([release](https://www.newswire.com/news/compliancequest-summer-26-expands-cq-ai-to-reduce-investigation-cycle-times), 2026-08-25, F, VC). The new BatchQuest EBR suite does not claim AI batch-record review ([release](https://www.newswire.com/news/compliancequest-announces-summer-26-release-accelerating-ai-powered-22835465), 2026-08-04, F, VC).
- **xLM Continuous Intelligence** — "GxP Software Validation Agents (Browser | Mobile | Desktop)" that "execute validation scripts autonomously, capture inspection-ready evidence."; an "RPA Agent" that "automates deviation management, CAPA orchestration, and SOP-driven workflows while maintaining full audit trails." No release status or named customer ([newsletter #095](https://continuoustv.beehiiv.com/p/095-the-frontier-qa-organization-governing-a-swarm-of-agents-in-gxp-pharma), c. 2026-02, F, VC).

**Drafting pipelines and assistants**
- **Dot Compliance** — "Dot Compliance Launches Dottie AI 5.0, Introduces Agentic AI Personas to Power the Future of Hybrid Workforces", 2026-04-21; Series B $23M (2022), $17.5M extension (2024) (headlines on the [news index](https://www.dotcompliance.com/?p=2590), F, VC; release body unavailable). Predefined agents: Research Agent, Review Agent, "Document to Protocol"; customers can "use predefined agents and/or create new ones." Whether agents create or fill records is not stated ([AI page](https://www.dotcompliance.com/ai), undated, F, VC).
- **Valkit.ai** — "Scoped drafts for requirements, risks, and tests — human review required, AI optional." ([homepage](https://valkit.ai/), undated, F, VC); its agentic page says the system "operates autonomously" ([page](https://valkit.ai/contextual-ai), undated, F, VC).
- **Sware Res_Q** — "Res_Q is an agentic GxP validation platform for life sciences."; no agents named ([product page](https://www.sware.com/res_q), undated, F, VC).
- **Raycaster** — YC Fall 2024, team of 6 ([YC profile](https://www.ycombinator.com/companies/raycaster), undated, F, VC). Agents "can take up requests to complete difficult, long-running tasks." "across Veeva, IQVIA, SharePoint, LIMS."; an agent "proposes a fix, and routes it to the right owner." ([Sacra interview](https://sacra.com/research/levi-lian-raycaster-vertical-ai-workflows/), 2025-10-02, F, VC: founder's statements).
- **Peer AI** — $12.1M led by Flare Capital Partners and SignalFire ([Pulse 2.0](https://pulse2.com/peer-ai-12-1-million-raised-to-advance-drug-approvals-with-intelligent-agentic-platform), 2025-10-21, F, VC rewrite). "Document-specific agents handle authoring across pre-clinical, CMC and clinical." ([homepage](https://www.getpeer.ai/), 2026-11-11, F, VC).
- **Weave Bio** — founded 2022, per a consultancy comparison that also says all performance figures in this category are vendor-supplied ([IntuitionLabs](https://intuitionlabs.ai/articles/ai-cmc-authoring-software-comparison), 2026-07-04, F, third party with a commercial interest). It "uses AI-assisted tools to support drafting, review, verification, source retrieval"; the homepage does not describe agents ([homepage](https://www.weave.bio/), undated, F, VC).

### Inferences
- "Agentic" here mostly means read-many, draft-one. I found no described case of an agent executing a transaction in MES, QMS, LIMS or ERP.
- Only Seal (save-time checks), Qualio (re-assessment on record change) and Katalyze (monitoring) describe a background trigger.
- xLM makes the strongest autonomy claims with the least detail on oversight or release status.

### Gaps
- No vendor documentation was readable. Seal's docs are "now served inside the product" behind sign-in ([docs.seal.run](https://docs.seal.run), F). ComplianceQuest's Summer '26 help pages returned a token login ([help site](https://help.compliancequest.com/summer-2026-help/cq-summer-26/end-user-help/platform-technology/cq-ai), F).
- Dottie AI 5.0 release text: the linked host has closed.

## 2. What interaction model presents agent work and gets human sign-off?

### Takeaway
Three patterns appear: a job queue whose output is a draft or changeset (Seal, Katalyze); review by exception with source references (Mareana); and assistants inside a record form or chat (ComplianceQuest, Dot, Qualio, Valkit). Chat is rarely the main surface.

### Cited Findings
- **Seal**: screens "Neil › Jobs" and "Neil › Checks › Today" with "6 to look at"; inline flags "To the analyst, before signing."; changesets "Awaiting signature"; "Every finding links to the record, version and field behind it."; "Neil drafts and proposes. It signs, approves and releases nothing."; permissions "Never more than the person asking it."; "It works by voice and by sight." ([seal.run/neil](https://seal.run/neil), F, VC).
- **Katalyze**: "Katalyze is the agent your teams talk to across the platform" ([homepage](https://www.katalyzeai.com/), F, VC). Runs are recorded ("Each run, with its owner, its sources and every decision."); drafts carry source footnotes and reviewer comments; "nothing moves downstream without a person" ([agentic solutions](https://www.katalyzeai.com/product/agentic-solutions), F, VC).
- **Mareana**: "color-coded dashboard" with "parameter cards with source snippets and one-click controls."; "Review By Exception"; "Dual Approval Workflows"; chain "value → rule → verdict → e-signature" ([product page](https://mareana.com/batch-review-copilot/), F, VC). Low-confidence reads are shown ("Read with low confidence, 0.71.") and "Routed to a reviewer."; items cited as "p. 37 · 6.5 Weight, kg"; "It never approves a record, releases a batch or decides a disposition." ([homepage](https://www.mareana.com/), F, VC).
- **Qualio**: "Ask Copilot a question, get an answer that cites your records"; each gap gets a recommended fix and a drafted procedure, change control or CAPA; "Nothing enters your quality system without a human approval, recorded with who, when and on what evidence." ([homepage](https://www.qualio.com), F, VC).
- **ComplianceQuest**: suggestions sit inside investigation and change-order forms; work goes "to your experts for approval as part of human in the loop at every aspect of the AI first quality platform" ([release](https://www.newswire.com/news/compliancequest-summer-26-expands-cq-ai-to-reduce-investigation-cycle-times), F, VC).
- **Dot Compliance**: "you are hiring digital personas."; "Agents can work proactively, route insights with context, and pause for expert approval before critical steps move forward." No e-signature, audit-trail or confidence wording ([AI page](https://www.dotcompliance.com/ai), F, VC).
- **Valkit**: "AI proposals" that SMEs "accept or dismiss"; "never auto-apply" ([homepage](https://valkit.ai/), F, VC).
- **Raycaster**: "workflows first, evaluators second, chat “anything” last."; "click to draft, click to edit, click to review." ([Sacra](https://sacra.com/research/levi-lian-raycaster-vertical-ai-workflows/), F, VC).

### Inferences
- The usual sign-off unit is a draft record or changeset signed in the host system, with an evidence link per finding. Explicit confidence display appears only at Mareana.
- Sware, xLM, Peer AI and Weave give no usable description of the review surface.

### Gaps
- No recorded demo or documentation was verified; UI descriptions rest on marketing-page annotations. Seal's example is declared fictional: "Blubber Biologics is a fictional plant." ([seal.run](https://seal.run/), F).

## 3. Does any entrant specifically offer agentic technology transfer?

### Takeaway
Two entrants describe agent-drafted transfer comparison (Seal, Katalyze); Seal alone names gap assessment and facility fit. Valkit MSAT covers transfer validation between sponsor and CDMO, and Raycaster covers transfer authoring. None has a named customer or independent evidence for this use case.

### Cited Findings
- **Seal**: "Neil compares the source process with the receiving plan" and "prepares a gap assessment with a proposed owner"; "Bind a platform process to a site's equipment, scale and facility constraints."; "Define responsibilities, permitted records and review access for each party."; "Neil can extract CPPs, ranges and rationale from PDFs, JMP files and workbooks into a changeset."; "each difference becomes owned work linked to both sources."; limit: "it does not approve equipment equivalence, validation or site readiness."; and "The lines on this page and Site B in the guide are fixed, fictional example records." ([blueprint](https://seal.run/blueprints/tech-transfer), undated, F, VC).
- **Katalyze**: the page describes a draft transfer comparison, open questions for the receiving team, supporting documentation, and action items with owner and status, drawing on Veeva Vault, SAP, Snowflake, SharePoint and CDMO records shared within an agreed scope; "authorized teams determine readiness". It does not name gap assessment, facility fit or scale-up prediction ([tech transfer](https://www.katalyzeai.com/solutions/tech-transfer), undated, F, VC). The July 2026 funding release omits tech transfer ([release](https://www.cxodigitalpulse.com/?p=57362), F, VC).
- **Valkit MSAT**: "Valkit MSAT runs GxP tech transfer between a sponsor and a CDMO as one controlled project."; "Clone complete validation packages and cross-pollinate transfer protocols and documents across organisations in seconds."; "AI generates protocol content with mandatory human review and e-signature before any record is finalised." No gap assessment, facility fit or open-item tracking ([MSAT page](https://valkit.ai/product/msat), undated, F, VC). General availability on 2026-04-27 is S only.
- **Raycaster**: launch use cases include "tech transfer authoring and QA, CTD-aligned specs, and RFPs for CDMOs/CROs." ([Sacra](https://sacra.com/research/levi-lian-raycaster-vertical-ai-workflows/), F, VC). A job ad turns tech-transfer packages "into steps an AI can execute with citations." and names Agilent and Yokogawa Life Sciences as customers ([job ad](https://standout.work/jobs/cmc-workflow-specialist-analytical-tech-transfer-at-raycaster), undated, F, VC).
- **Peer AI**: an anonymous case turns "data-dense, color-coded PDFs from a manufacturing partner" into IND Module 3 prose ([case study](https://www.casestudies.com/company/peer-ai/case-study/how-a-public-biotech-company-used-peer-ai-to-improve-cmc-document-quality), undated, F, VC).
- **Independent context**: a trade feature on AI in tech transfer names no vendor; its source says "AI can't fix disorganized data or an inherently shaky process." ([Outsourced Pharma](https://www.outsourcedpharma.com/doc/how-ai-is-rewriting-tech-transfer-timelines-0001), 2025-11-26, F, IE).

### Inferences
- Sponsor–CDMO open-item tracking exists only as marketing description: Seal's owned differences and Katalyze's open-question list.
- Transfer is a secondary use case for every entrant; none is built around it.

### Gaps
- No public evidence found of a completed transfer run with these tools. Queries tried: `AI agents technology transfer biopharma startup process gap assessment facility fit`; `startup raises seed AI agents CMC MSAT "tech transfer" biologics CDMO 2026`; `"Valkit MSAT" tech transfer CDMO validation launch`.

## 4. What independent evidence exists?

### Takeaway
Independent sources confirm funding, corporate facts and a few customer relationships. None confirms agent behaviour in production. No customer-authored talk, user review or peer-reviewed paper was found for any entrant.

### Cited Findings
- **Katalyze**: BetaKit says it is "already used by five of the world's 20 biggest," including Sanofi ([BetaKit](https://betakit.com/katalyze-ai-thinks-the-future-of-pharma-operations-is-teams-of-ai-agents/), F, IE; origin of the figure not stated). A Scale AI (Canada) page lists "AI-enabled Raw Material Characterization for the Drug Manufacturing Supply Chain", "Working alongside Sanofi Canada", total investment $0.6M ([project page](https://www.scaleai.ca/funded-projects/ai-enabled-raw-material-characterization-for-the-drug-manufacturing-supply-chain/), undated, F, IE). Sanofi's Sabya Dasgupta: "built for an enterprise like Sanofi from day one." ([vendor release](https://www.cxodigitalpulse.com/?p=57362), 2026-07-07, F, VC). One outlet calls the claims "vendor-reported until deployment evidence is published." ([LetsDataScience](https://letsdatascience.com/news/katalyze-ai-raises-105m-to-deploy-agent-teams-238c1d75), 2026-07-06, F, IE). Vendor figures conflict: the release cites a year-long, $4–6M analysis done in 45 minutes; the website shows "a year and $1.5-3M" done in "2 days".
- **ComplianceQuest**: at ConQuest 2025 the CTO was "outlining the organization's vision for AI agents"; attendees including Johnson & Johnson and Standard BioTools were "deeply absorbed by the vision for AI agents" but said "it would take a steep amount of AI governance frameworks"; the analyst adds "human oversight should prevent AI agents from acting autonomously." ([Verdantix](https://www.verdantix.com/insights/blog/conquest-2025-highlights-the-significance-of-context-aware-ai-agents-in-ehsq), 2025-04-23, F, IE). Analyst rankings and an FDA selection are S or headline only.
- **Dot Compliance**: Axendia's post is briefing-based ("Axendia was recently briefed by the executive team at Dot Compliance.") and notes "the nuts and bolts behind Dottie are proprietary and not available for public disclosure" ([Axendia](https://axendia.com/blog/2023/09/01/say-hello-to-dottie-combining-quality-compliance-and-production-optimization-with-ai/), 2023-09-01, F, IE, pre-agentic).
- **Weave Bio**: "Weave Bio has deployed its AI-driven regulatory submission platform across 14 of Takeda's drug programs."; "No submission timeline data or agency acceptance outcomes have been disclosed at this stage." ([PharmaNow](https://www.pharmanow.live/latest-news/weave-bio-takeda-ai-regulatory-platform-14-drug-programs), 2026-09-04, F, VC: press-release rewrite).
- Seal, Mareana, Qualio, Valkit, Sware, xLM, Raycaster, Peer AI: no public evidence found beyond vendor material (queries below).

### Inferences
- The best-evidenced entrant is Katalyze, and only for existence, funding and a Sanofi relationship.

### Gaps
- Queries run without independent hits: `Seal GxP platform "Neil" AI agent MES LIMS QMS customers review MiAlgae Paradromics`; `Katalyze AI Sanofi OR Pfizer OR GSK case study presentation ISPE OR PDA OR "BioProcess International" agents`; `Mareana "Batch Review Copilot" OR "agentic platform" pharma manufacturing founded funding customers`; `"Dottie AI 5.0" Dot Compliance launches agentic personas press release`; `Sware Res_Q agentic AI validation agents`; `xLM Continuous Intelligence AI agents GxP validation`.
- Blocked or not run: G2 (Dot Compliance) returned 403; searches for Qualio user reviews, "Lighthouse", Humigent, and Synthace/Cellares/BioRaptor agents hit the search-budget limit; Reddit, conference-agenda and Gartner/IDC/LNS searches were never run.

## 5. What do they say about GxP validation of the agent, audit trails and human-in-the-loop?

### Takeaway
The more specific vendors place the agent outside GMP decision-making and leave intended-use validation to the customer. Only Seal describes re-evaluating the agent when the model changes. Katalyze says electronic signatures are not yet shipped.

### Cited Findings
- **Seal**: validated "By your QA, job by job. On your own cases, against criteria your experts set."; "It's evaluated again. On the same cases, before the new model is used." ([seal.run/neil](https://seal.run/neil), F, VC). "In line with the EU's draft GMP Annex 22, Neil decides nothing in GMP work."; records have "controls to support 21 CFR Part 11 and EU GMP Annex 11." ([platform](https://seal.run/platform), undated, F, VC). Its regulatory page says draft Annex 22 "says large language models should not be used in critical GMP applications." ([regulatory](https://seal.run/regulatory), undated, F, VC).
- **Katalyze**: "Supplier documentation aligned to GAMP 5 expectations for supplier-provided evidence."; "Tamper-evident audit trails with an independent chain verifier and seven-year retention."; "Agent, prompt, and skill versions are captured with each run."; "Katalyze does not approve a batch, close a deviation, or release a product."; "Electronic signatures are planned"; SOC 2 Type II audited February 2026 ([compliance](https://www.katalyzeai.com/compliance), undated, F, VC).
- **Mareana**: validates the platform and its AI under GAMP 5 and hands over the package; Part 11 and Annex 11 compliance is "Shown through validation and control evidence, not a certificate." ([homepage](https://www.mareana.com/), F, VC). The product page also says the model "retrains on reviewer decisions under strict validation logging protocols" ([product page](https://mareana.com/batch-review-copilot/), F, VC).
- **Qualio**: "ISO 42001-certified AI, approval-gated."; "A validation pack ships with every major release" ([homepage](https://www.qualio.com), F, VC).
- **ComplianceQuest**: "operation within Salesforce's Einstein Trust Layer" ([Summer '25 release](https://www.newswire.com/news/compliancequest-unveils-summer-25-release-cq-ai-agents-usher-in-a-new-22649339), 2025-10-02, F, VC).
- **Valkit**: "STAR for AI Level One: Self-Assessment" ([MSAT page](https://valkit.ai/product/msat), F, VC). **Sware**: "ensures every decision is explainable, traceable, and reversible"; no approval step stated ([release](https://markets.financialcontent.com/dowtheoryletters/article/bizwire-2025-10-21-sware-launches-enhanced-ai-powered-res_q-platform-to-advance-gxp-validation-in-life-sciences), 2025-10-21, F, VC).
- **xLM**: neither human approval nor agent validation is described; "QA governs the rules; the URS Agent enforces them" ([newsletter #095](https://continuoustv.beehiiv.com/p/095-the-frontier-qa-organization-governing-a-swarm-of-agents-in-gxp-pharma), F, VC). **Dot Compliance**: "expert-in-the-loop controls built into the way agents work."; no validation or Part 11 statement about the AI ([AI page](https://www.dotcompliance.com/ai), F, VC).
- **Peer AI, Weave**: no GxP or Part 11 statement (homepages, F). **Raycaster**: drafting work is "typically non-GMP and non–Part 11." ([Sacra](https://sacra.com/research/levi-lian-raycaster-vertical-ai-workflows/), F).
- **Independent benchmark**: ISPE's journal says "Accountability does not transfer to the agent; the qualified person retains full responsibility", and cites "a 2026 warning letter citing inappropriate use of AI to generate drug product specifications." ([Pharmaceutical Engineering](https://ispe.org/pharmaceutical-engineering/july-august-2026/accelerating-decision-velocity-digital-transformations), Jul/Aug 2026, F, IE).

### Inferences
- "Agent proposes, human signs" is the standard posture, matching the ISPE position and draft Annex 22 as Seal characterises it.
- Mareana's retraining statement sits awkwardly with a validated state; the page does not explain how retraining is controlled.

### Gaps
- No validation package, supplier-assessment document or audit report was publicly readable for any entrant.

## Closing summary

| Entrant | Where AI lives | What it does | Approval model | Status / date | Evidence quality |
|---|---|---|---|---|---|
| Seal (Neil) | Jobs list, checks queue, inline flags, changeset review, voice | Reads records and connected systems; drafts deviations, batch-review findings, gap assessments, changesets | Proposes only; QA signs; finding links to record, version, field | Live, no GA label; undated | VC, detailed; demo fictional; docs gated |
| Katalyze AI | Chat agent, assigned jobs, run records | Multi-source deviation, yield, raw-material and transfer drafts with citations | Draft for expert review; e-signatures planned | Katalyst 2026-01-20; seed 2026-07 | VC for behaviour; IE for funding and Sanofi link |
| Mareana | Review-by-exception dashboard | Digitises and checks batch records; CPV charts; drafts annual review | Never approves or releases; low-confidence fields routed; e-signature | Six modules live, EBR beta; undated | VC; logos only |
| ComplianceQuest | In-form assistants; Agentforce agents | Suggests root causes; drafts change orders; Safety Agent pre-populates incidents | Human in the loop; experts approve | Summer '26 GA 2026-07-31 | VC; IE note on 2025 vision; docs gated |
| Dot Compliance | Persona agents, dialogues, proactive prompts | Research, review, document-to-protocol; custom agents | Pause for expert approval | Dottie AI 5.0, 2026-04-21 | VC; analyst post pre-agentic |
| Qualio | Copilot chat, gap records, MCP | Clause-level assessment; drafts SOP, change control, CAPA | Approval-gated, approval recorded | Compliance Intelligence GA 2025-10; rest "building" | VC |
| Valkit.ai | Inside validation authoring | Drafts requirements, risks, tests; MSAT clones packages sponsor to CDMO | Mandatory review and e-signature | MSAT GA 2026-04-27 (S) | VC |
| Sware Res_Q | Not specified | Monitoring flags, risk scoring, video-to-script | Step not stated | Release 2025-10-21 | VC, thin |
| xLM | Not specified | Claims autonomous test execution and CAPA orchestration | Not described | Status not stated | VC, vision-level |
| Raycaster | Document workspace | Long-running document tasks incl. transfer authoring | Experts approve actions | YC F24; interview 2025-10 | VC (founder) |
| Peer AI | Authoring platform, API/MCP | Agent pipeline drafts regulatory and CMC documents | Expert review; outputs traced to source | $12.1M 2025-10 | VC; anonymous cases |
| Weave Bio | Submission builder | AI-assisted drafting, review, verification | Humans decide; source links | Takeda release 2026-09 | VC with named-customer release |

**Technology transfer.** Seal is the only entrant whose public material describes sending-versus-receiving comparison, a gap assessment with a proposed owner per difference, facility-fit binding and party-level access for sponsor and CDMO; its example records are declared fictional. Katalyze lists Tech Transfer among four solutions that "Run today" and describes a comparison view, open questions and drafted plans, without naming gap assessment or facility fit. Valkit MSAT addresses a transfer's validation documents, not process gaps. Raycaster and Peer AI address transfer and CMC authoring. None shows a completed transfer, a named customer or independent coverage.

**Dropped or adjacent**
- BioRaptor ([site](https://www.bioraptor.ai/), F) and DataHow ([site](https://www.datahow.ch/), F): bioprocess analytics and modelling; no agent claim.
- Synthace ([site](https://www.synthace.com/), F): drug-discovery experiment design. Cellares ([site](https://www.cellares.com/), F): sells manufacturing services, not software.
- Scispot ([Scibot](https://www.scispot.com/scibot), F): agent features ("Record changes await required approval") but for R&D and clinical labs.
- Leucine: MES/QMS founded 2019, $7M Series A, AI framework in beta in 2023 ([TechCrunch](https://techcrunch.com/2023/10/16/leucine/), 2023-10-16, F, IE). Its site offers "AI-powered root cause analysis and CAPA recommendations" and "exception-based" batch review without using "agent" ([leucine.io](https://www.leucine.io/), F, VC).
- Artos ([site](https://www.artosai.com/), F): YC document authoring, no agent or CMC detail. Bluenote ([Anthropic story](https://claude.com/customers/bluenote), F, partner co-marketing): regulatory and clinical document agents; names Guardant Health and Eledon.
- LogicFlo AI: $2.7M seed; writing agents incl. deviation reports and CAPAs ([HIT Consultant](https://hitconsultant.net/2025/06/30/logicflo-ai-secures-2-7m-to-optimize-life-sciences-with-ai-agent-workforce/), 2025-06-30, F). Validfor: $1.2M pre-seed; "Autonomous Testing" planned ([BriefGlance](https://briefglance.com/articles/validfors-12m-ai-bet-to-overhaul-pharma-compliance), 2026-02-24, F).
- Trilo: only Trilobio, a lab-robotics firm, surfaced (S). iFactory AI: marketing post for an agentic transfer gap report ("The LLM never closes a gap."), no customer named ([post](https://ifactoryapp.com/sap-integration/on-prem-ai/tech-transfer-digital-twin), 2026-05-05, F, VC). ZS, StackAI, Aganitha, Kolter AI: consultancy pilot, generic builder, services, unrelated engine.

**Could not establish**
- Seal: funding, Neil's launch date, real-customer use of Neil.
- Katalyze: whether "Katalyst" equals today's "Katalyze" agent; which five top-20 firms; any write-back.
- Mareana: founding year, funding, launch date of agentic modules, whether logos are current customers.
- ComplianceQuest: agent actions in help docs (gated); founding and funding. Dot Compliance: Dottie 5.0 release content; whether agents write records.
- Qualio: which of Copilot, CI Agents, Beacons and MCP are shipped. Valkit, xLM, Sware: release status, customers.
- Leucine's current offering (leucine.ai returned 403). "Lighthouse": not identified; query not run.
- Iridius ($8.6M seed), Humigent, Cheiron: snippets only.
- User reviews, customer conference talks, Gartner/IDC/LNS notes: none found; several searches not run.
