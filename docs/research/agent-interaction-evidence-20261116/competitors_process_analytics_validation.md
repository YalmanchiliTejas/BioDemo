# Competitor AI / agent evidence: Quartic.ai, Aizon, Basetwo, QbDVision, ValGenesis, Kneat (as of 2026-11-16)

Reading rules
- Each claim has an inline `[ID](URL)`. The source key gives date, F (FETCHED) or S (SNIPPET), and label: VC vendor claim, VD vendor documentation, IE independently evidenced.
- Nothing is VD: no vendor's help-centre or release-note text on AI was publicly reachable.
- Quotes are as returned by the page-reader tool; spot-check before reprinting.
- Linked text is "source states". My reading is under "Inferences".

## KQ1. Does any vendor ship an agent that takes multi-step actions on its own, or is everything prompt-in / draft-out or a predictive model with a dashboard?

### Takeaway
No public evidence found of a generally available background, event- or schedule-triggered, cross-system agent at any of the six. Generative features are user-invoked and end in a draft, a flag list, a cited answer or a generated dashboard that a person accepts. The only "acts without an operator" items are non-LLM: Basetwo's research demo of model-predictive control, and an unspecified "closes the loop ... within defined guardrails" claim for ParkourSC + Quartic.

### Cited Findings

#### Source key
Format: ID, source, date, tag/label.
- Quartic: Q1 ParkourSC press release (PRWeb), 14 Oct 2026, F/VC. Q3 Remio.ai commentary (low-authority blog), "Oct 15" year not shown, F/IE-weak. Q4 quartic.ai home page, undated (c) 2026, F/VC. Q5 GBR interview with CEO R. Anand, undated 2025 edition, F/VC.
- Aizon: A1 home page, undated (c) 2026, F/VC. A2 Agentic Studio page, undated, F/VC. A3 "For LLMs" fact page, undated 2026, F/VC. A4 launch blog, 19 Feb 2026, F/VC. A5 batch-release blog, 22 Feb 2026, F/VC. A6 APQR blog, 4 May 2026, F/VC. A8 GEN feature, 9 Mar 2026, F/IE (trade press built on a vendor interview). A9 Bioprocess Online, "Source: Aizon" (intro only; body gated), 28 May 2025, F/VC. A10 yespress.io profile, undated, S/third-party aggregator.
- Basetwo: B1 home page, undated (c) 2026, F/VC. B2 platform page, undated, F/VC. B3 scale-up / tech-transfer page, undated, F/VC. B4 Applied Research Labs post, Nov 2026, F/VC (research). B5 announcement with partner quotes, "Nov 11" year not shown, F/VC. B6 Process Verification announcement, 20 Jun 2025, F/VC. B7 GEN article, 29 Jun 2022, F/IE. B8 GlobeNewswire via StreetInsider, 27 May 2026, S/VC. B9 docs.basetwo.ai, undated, F (access-code gate only).
- QbDVision: V1 AI platform page with FAQ, undated (c) 2026, F/VC. V2 AWS Startups article, 27 Aug 2026, F/VC (partner-authored). V3 vendor blog, 8 Jun 2026, F/VC. V4 vendor blog, 10 Aug 2026, F/VC. V7 Business Wire financing release, 1 May 2025, S/VC.
- ValGenesis: G1 white paper "Ensuring Trust in AI", 3 Oct 2025, F/VC (technical). G2 press release, 14 Apr 2026, F/VC. G3 press release, 22 Oct 2025, F/VC. G4 press release, 27 Mar 2025, F/VC. G5 "AI-native GxP validation" page with FAQ, undated (c) 2026, F/VC. G7 home page, undated 2026, F/VC. G8 Axendia briefing note, 17 Dec 2024, F/IE (vendor-briefed). G9 news index, to Oct 2026, F/VC. G10 press release, 2 Oct 2026, F/VC.
- Kneat: K1 webinar page "The Kneat AI Advantage", 15 Apr 2026, F/VC (states limits; the one-document quote was seen in a search snippet of the page). K2 article "Kneat Gx 26R2", 7 Sep 2026 (page also shows "updated 27 Jul 2026"), F/VC. K5 Thoma Bravo press release, 11 Aug 2026, F/IE (acquirer). K6 Yahoo Finance / MarketBeat summary of Q4 2025 earnings call, c. Feb 2026, F/IE report of management statements. K8 G2 listing, undated, S/IE.

#### Quartic.ai (now a ParkourSC company)
- (a) Where: no chat, assistant or LLM surface found. A DataOps layer (iLuminator), a modelling engine (eXponence: "Apply MVDA, ML, and optimization for quality and yield.") and monitoring / optimisation apps (Process Optimizer: "AI-powered process control for yield, quality, and diagnostics.") — [Q4](https://www.quartic.ai/)
- (b) Does: predictive and multivariate models; Automated Decision Systems: "Reduces manual input by executing logic-based decisions at speed." — [Q4](https://www.quartic.ai/). Parent says the combined platform will "predict[s] which batches, lots, and shipments are at risk and prescribe[s] the best course of action" and "closes the loop from detection and stability budget assessment through disposition and the evidence record, within defined guardrails."; the release never says "agent"; write-back unspecified — [Q1](https://www.prweb.com/releases/parkoursc-acquires-quartic-launching-the-first-unified-ai-platform-that-predicts-and-prevents-quality-risk-across-the-entire-life-sciences-value-chain-302908249.html)
- (c) Approval: not described. "The announcement does not detail how those guardrails vary by context, customer, or regulated decision." — [Q3](https://www.remio.ai/post/parkoursc-quartic-acquisition-connects-factory-data-to-the-drug-supply-chain)
- (d) Status: "Quartic is now a ParkourSC company." (14 Oct 2026; terms undisclosed) — [Q1](https://www.prweb.com/releases/parkoursc-acquires-quartic-launching-the-first-unified-ai-platform-that-predicts-and-prevents-quality-risk-across-the-entire-life-sciences-value-chain-302908249.html). CEO, 2025: "Full autonomy in production is still far away." — [Q5](https://projects.gbreports.com/us-life-sciences-2025/quarticai-interview)
- (e) Beyond vendor: only [Q3](https://www.remio.ai/post/parkoursc-quartic-acquisition-connects-factory-data-to-the-drug-supply-chain), which notes the outcome figures are company-reported.
- (f) Evidence quality: LOW. Generative AI or agents: no public evidence found.

#### Aizon
- (a) Where: Agentic Studio, a separate product on the Aizon platform; prompt in, generated web app or dashboard with live preview: "Build dashboards and converse with your data in natural language, no coding required" — [A1](https://www.aizon.ai/), [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language)
- (b) Does: agent "securely accesses the data on the Aizon platform through an API", builds the app, exports Word/PDF with "audit signatures and data hashes" — [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language). APQR: pulls cross-batch LIMS, ERP, MES data into a "dynamic draft" for SMEs — [A6](https://www.aizon.ai/blog/apqr-on-demand-how-aizon-agentic-studio-turns-months-of-work-into-minutes). It "does not invent or generate data" — [A3](https://www.aizon.ai/2026/for-llms). Record writes, triggers, schedules: not described. Batch-release post defines agentic AI generally; no shipped release agent — [A5](https://www.aizon.ai/blog/accelerating-batch-release-with-agentic-ai). 2025 claim: "intelligent agents" that "execute Operational and Performance Qualifications (OQ/PQ) on demand" — [A9](https://www.bioprocessonline.com/doc/from-weeks-to-days-how-aizon-intelligent-agents-transform-pharma-validation-0001)
- (c) Approval: "The agent never publishes autonomously."; user previews, iterates, approves; "The application uses code to fetch real, live, deterministic data." — [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language). Generated apps are "audit-ready so you can easily validate them" — [A2](https://www.aizon.ai/agentic-studio). E-signature on AI output: not stated.
- (d) Status: introduced 19 Feb 2026, no version or GA wording — [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language). Aggregator snippet: pre-announced Oct 2025, "general availability targeted for early Q1 2026" — [A10](https://yespress.io/aizon). Site footer reads "Bigfinite Inc., dba Aizon"; no acquisition or wind-down found — [A1](https://www.aizon.ai/)
- (e) Beyond vendor: GEN reports LLMs integrated while "introducing the control mechanisms recommended by good manufacturing practices (GMP)", with a natural-language APQR request producing a dashboard; built on a co-founder interview — [A8](https://www.genengnews.com/topics/artificial-intelligence/smarter-filings-smarter-factories/). No customer evidence specific to Agentic Studio found.
- (f) Evidence quality: LOW-MEDIUM.

#### Basetwo
- (a) Where: agent inside a modelling workbench (workflow canvas, "agent-assisted modeling", dashboards where users "ask what happened or what to do next"); panel placement not stated — [B2](https://www.basetwo.ai/platform)
- (b) Does (marketed): home-page demo of a "tech transfer" agent run: ingests historian batch records, drops drifting runs, fits and validates a hybrid model, simulates 1,200 feed profiles, queues a draft transfer package (reader paraphrase) — [B1](https://www.basetwo.ai/). Stated flow: ingest historian, MES, LIMS, SOP data; model; simulate; draft "run plan or transfer package" — [B3](https://www.basetwo.ai/applications/process-scale-up-and-tech-transfer). Plant actions stay with users: "Users can apply and visualize the effect of recommendations before implementing them on the plant floor." — [B2](https://www.basetwo.ai/platform). Research demo: controller "writes the setpoint straight to the feed pump every four hours, within limits the team sets" (hybrid model, Kalman filter, MPC; small-scale reactors; not an LLM agent) — [B4](https://www.basetwo.ai/applied-research-labs/autonomous-closed-loop-bioreactor-control)
- (c) Approval: drafts "for review" from an "approved model version" — [B3](https://www.basetwo.ai/applications/process-scale-up-and-tech-transfer). "End-to-end audit trails for all data, models, and decisions" — [B2](https://www.basetwo.ai/platform). Approval gate, e-signature, AI validation method: not described.
- (d) Status: agent positioning live Nov 2026, undated, no version — [B1](https://www.basetwo.ai/). Boilerplate changed from "the digital twin platform for process development and manufacturing" (27 May 2026) — [B8](https://www.streetinsider.com/Press+Releases/Basetwo+Selected+for+Canada%E2%80%99s+AI+Compute+Access+Fund/26555266.html) — to "agentic digital twin software" — [B5](https://www.basetwo.ai/announcements/basetwo-demonstrates-bioreactor-closed-loop-control-for-a-breast-cancer-therapeutic). Non-agent Process Verification is GA: "now available to all Basetwo customers across their company workspaces." — [B6](https://www.basetwo.ai/announcements/basetwo-launches-new-process-verification-capability). No acquisition or wind-down found. Docs "Access Restricted" — [B9](https://docs.basetwo.ai/)
- (e) Beyond vendor: 2022 GEN piece, pre-agent: no-code digital twins used by a Johnson & Johnson Innovation team — [B7](https://www.genengnews.com/insights/ai-can-make-a-difference-on-the-factory-floor-if-biopharma-invests/). Partner quotes sit inside the vendor release — [B5](https://www.basetwo.ai/announcements/basetwo-demonstrates-bioreactor-closed-loop-control-for-a-breast-cancer-therapeutic)
- (f) Evidence quality: LOW (agent evidenced only by marketing pages).

#### QbDVision (AI features only)
- (a) Where: "Qurio" inside QbDVision: "Insights by Qurio" (natural-language Q&A) and "Import by Qurio" (PDF to structured records); UI placement not described — [V1](https://www.qbdvision.com/platform/ai), [V4](https://www.qbdvision.com/resources/ai-credibility-cmc)
- (b) Does: "Retrieve records and data, and get direct links to sources using natural-language questions."; "Compare process parameters, quality attributes, and control strategies in a structured table." — [V1](https://www.qbdvision.com/platform/ai). Import: "helping turn information trapped in PDFs into structured, auditable CMC records" — [V2](https://aws.amazon.com/aws-startups/learn/building-scalable-ai-for-cmc-qbdvision-amazon-bedrock/). Document drafting, workflow triggers, external connectors, MCP: not mentioned. "We never use AI for autonomous decision-making." — [V3](https://www.qbdvision.com/building-scalable-ai-for-cmc/)
- (c) Approval: "AI-generated outputs remain subject to human review and approval before they become part of a GxP-impacted record."; "the system distinguishes the AI-generated suggestion from the final version reviewed and accepted by the user."; "AI features are not enabled by default and are activated only after the customer confirms readiness."; "we currently use Anthropic Claude through Amazon Bedrock"; completeness 94.2%, correctness 92.7%, "225+" evaluation tasks — [V1](https://www.qbdvision.com/platform/ai). Per-feature credibility assessment plans under a master plan — [V4](https://www.qbdvision.com/resources/ai-credibility-cmc). Model, prompt, schema and code versions recorded per result — [V3](https://www.qbdvision.com/building-scalable-ai-for-cmc/)
- (d) Status: no dated GA announcement; "launching AI-based tools" (27 Aug 2026) — [V2](https://aws.amazon.com/aws-startups/learn/building-scalable-ai-for-cmc-qbdvision-amazon-bedrock/); "excited to be developing scalable AI" (8 Jun 2026) — [V3](https://www.qbdvision.com/building-scalable-ai-for-cmc/). Venture-backed ($13M round, May 2025); no acquisition found — [V7](https://www.businesswire.com/news/home/20250501667352/en/QbDVision-Secures-13M-in-New-Financing-to-Accelerate-Digital-CMC-Transformation-and-Product-Lifecycle-Management-for-Enterprise-Pharma-and-Biotech/)
- (e) Beyond vendor: AWS partner article only — [V2](https://aws.amazon.com/aws-startups/learn/building-scalable-ai-for-cmc-qbdvision-amazon-bedrock/). No demo, review or customer talk found.
- (f) Evidence quality: LOW-MEDIUM.

#### ValGenesis
- Naming: "Process Manager (for cleaning validation)", "Process Insights for CPV", "iRisk (risk management for the CMC process)" — [G8](https://axendia.com/blog/2024/12/17/powering-smart-manufacturing-in-life-sciences/). Current site lists iVal, iClean, iOps, iCMC, iCPV — [G7](https://www.valgenesis.com)
- (a) Where: "VAL is the ValGenesis AI agent built into the Validation Lifecycle Suite (VLS)."; no chat surface described — [G5](https://www.valgenesis.com/smart-gxp/ai-native-gxp-validation)
- (b) Does: VAL 1.0 "Smart Agents": Document Generator (drafts, updates protocols), Gap Assessor, Validation Executor (test results from captured evidence), Anomaly Detector; they "do not operate autonomously or interface with GMP critical systems" — [G1](https://www.valgenesis.com/editorial/ensuring-trust-in-ai-the-valgenesis-approach-to-validating-ai-agents-and-functions-for-validation-and-qualification-in-life-sciences). Next generation: Author, Examine, Analyze, Trace, Compare, Summarize — [G5](https://www.valgenesis.com/smart-gxp/ai-native-gxp-validation). iCMC "ML-powered trend analytics"; iCPV "Multivariate analytics, SPC control charts, and guided workflows"; no LLM or agent claim there — [G7](https://www.valgenesis.com)
- (c) Approval: "Every key output from a Smart Agent is subject to human review."; drafts stay drafts until a qualified reviewer approves (reader paraphrase); "Each Smart Agent interaction is logged with a complete audit trail, including user identity, date, time, and action taken."; IQ/OQ/PQ; "Any change to an AI component triggers a full revalidation cycle."; "VAL 1.0 is powered by LLMs with a knowledge cutoff of October 2023." — [G1](https://www.valgenesis.com/editorial/ensuring-trust-in-ai-the-valgenesis-approach-to-validating-ai-agents-and-functions-for-validation-and-qualification-in-life-sciences). E-signature on AI output, model provider: not stated.
- (d) Status: VLMS 5.0, "a new AI-enabled validation solution" — [G8](https://axendia.com/blog/2024/12/17/powering-smart-manufacturing-in-life-sciences/) — dated 4 Jun 2024 — [G9](https://www.valgenesis.com/news/page/1). VAL unveiled 27 Mar 2025 with an Early Adopter Program — [G4](https://www.valgenesis.com/news/valgenesis-to-unveil-ai-enabled-digital-validation-at-interphex-2025). "kicked off a pilot program with select customers" (22 Oct 2025) — [G3](https://www.valgenesis.com/news/valgenesis-to-showcase-ai-enabled-validation-at-2025-ispe-annual-meeting-and-expo). VAL "can be activated today" for iVal customers (Oct 2025) — [G1](https://www.valgenesis.com/editorial/ensuring-trust-in-ai-the-valgenesis-approach-to-validating-ai-agents-and-functions-for-validation-and-qualification-in-life-sciences). Next generation, 14 Apr 2026: "open a limited pilot program for qualified life sciences companies" — [G2](https://valgenesis.com/news/valgenesis-launches-the-next-generation-of-val-bringing-governed-ai-to-the-validation-lifecycle). Oct 2026 talks cite "customer pilot studies" — [G10](https://www.valgenesis.com/news/valgenesis-to-bring-real-world-ai-assisted-validation-insights-to-kenx-europe-2026). No GA announcement or ownership change listed; $16M financing 22 Jul 2025 — [G9](https://www.valgenesis.com/news/page/1)
- (e) Beyond vendor: Axendia note is vendor-briefed and predates VAL: "We can imagine a future state where validation programs are automated by AI." — [G8](https://axendia.com/blog/2024/12/17/powering-smart-manufacturing-in-life-sciences/). Vendor-run pilot: "Up to 56%" less authoring effort per page, 46 documents — [G5](https://www.valgenesis.com/smart-gxp/ai-native-gxp-validation). No named VAL customer or independent result.
- (f) Evidence quality: LOW-MEDIUM.

#### Kneat (Kneat Gx)
- (a) Where: inside Kneat Gx: navigation chat; AI Review Assistant on test-execution documents; AI Validation Expert chatbot "built into Kneat Gx"; Validation Summary Report Agent on documents — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/), [K2](https://kneat.com/?p=16587)
- (b) Does: Review Assistant flags blank fields, expected/actual mismatches, missing evidence; checks screenshots with OCR plus a language model — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/). Validation Expert answers from "FDA, EMA, ICH, ISO, and GAMP knowledge sources" with citations; Summary Agent "Generates Issue, Test, and Executive Summary sections in In Development documents" from post-approved test documents across workspaces — [K2](https://kneat.com/?p=16587)
- (c) Approval: "Every AI feature follows a human-in-the-loop principle, meaning SMEs review and approve all AI-generated suggestions."; Review Assistant "currently reviews one document at a time and its findings are advisory — it does not block approvals"; foundation models, no training on customer data — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/). "Controlled enablement and governed configuration, so admins decide how and where it's used." — [K2](https://kneat.com/?p=16587). AI-specific audit trail, e-signature, AI validation method: not stated.
- (d) Status: released by 15 Apr 2026: chat, AI-translated UI, AI Review Assistant; roadmap into 2027: AI authoring, risk scoring, cross-document review, virtual inspection agent — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/). Kneat Gx 26R2 adds Validation Expert and Summary Report Agent — [K2](https://kneat.com/?p=16587). Thoma Bravo completed the take-private 11 Aug 2026 (about C$650M): "Shares of Kneat have ceased trading and will be delisted from the Toronto Stock Exchange."; the release calls the AI capabilities "Optional" — [K5](https://www.thomabravo.com/press-releases/thoma-bravo-completes-acquisition-of-kneat)
- (e) Beyond vendor: CEO on the Q4 2025 call: customers want AI as a "human aid"; Kneat is "not seeing anybody sitting on top" of its data with AI layers — [K6](https://finance.yahoo.com/news/kneat-com-q4-earnings-call-113044763.html). G2: 4.5 from 97 reviews; no AI-specific review text surfaced — [K8](https://www.g2.com/products/kneat/reviews)
- (f) Evidence quality: LOW-MEDIUM (limits stated plainly; no documentation or independent usage evidence).

### Inferences
- Three interaction shapes cover everything found: ask-and-answer with citations (Qurio Insights, Kneat Validation Expert); invoke on a record and get a draft or flag list (VAL, Kneat Review Assistant and Summary Agent, Qurio Import); prompt-to-artifact builder (Aizon Agentic Studio, Basetwo's agent as marketed).
- Where AI content lands in the system of record (Kneat Summary Agent, ValGenesis generator and executor, Qurio Import), it lands as a draft or suggestion ahead of the existing human approval route. This is stated for ValGenesis and QbDVision and inferred for Kneat from the "In Development" document state.
- "Agent" is mostly a label: ValGenesis applies it to invoke-and-review functions, Aizon to a dashboard builder; the ParkourSC + Quartic release avoids the word.
- Basetwo's site describes the most agent-like behaviour and is the least verified: no date, documentation or third-party account.
- Aizon's "so you can easily validate them" implies the customer validates each generated app.

### Gaps
- Whether any feature runs without a user starting it (schedules, events): sources are silent, which is not proof of absence.
- Actual UI placement for Qurio, VAL and Basetwo's agent: not shown in any reachable source.

## KQ2. Which features are generally available versus announced, beta or roadmap, and as of what date?

### Takeaway
Only Kneat states "released" for named AI features. ValGenesis VAL has run early-adopter and pilot programmes since March 2025 with no GA announcement found. Aizon, Basetwo and QbDVision present AI as current without versions, release notes or GA wording.

### Cited Findings
- Stated as released: Kneat chat, translated UI, Review Assistant (by 15 Apr 2026) — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/); Validation Expert and Summary Report Agent in 26R2 (article dated 7 Sep 2026) — [K2](https://kneat.com/?p=16587); Basetwo Process Verification, non-agent (20 Jun 2025) — [B6](https://www.basetwo.ai/announcements/basetwo-launches-new-process-verification-capability)
- Pilot: ValGenesis VAL, Early Adopter Program (27 Mar 2025) to "limited pilot program" (14 Apr 2026) — [G4](https://www.valgenesis.com/news/valgenesis-to-unveil-ai-enabled-digital-validation-at-interphex-2025), [G2](https://valgenesis.com/news/valgenesis-launches-the-next-generation-of-val-bringing-governed-ai-to-the-validation-lifecycle)
- Presented as current, no GA wording: Aizon Agentic Studio (19 Feb 2026) — [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language); QbDVision Qurio, opt-in, "launching" (27 Aug 2026) — [V2](https://aws.amazon.com/aws-startups/learn/building-scalable-ai-for-cmc-qbdvision-amazon-bedrock/); Basetwo agents (Nov 2026) — [B1](https://www.basetwo.ai/)
- Roadmap or research: Kneat AI authoring, cross-document review, virtual inspection agent — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/); Basetwo closed-loop control — [B4](https://www.basetwo.ai/applied-research-labs/autonomous-closed-loop-bioreactor-control)
- None found: Quartic generative AI — [Q4](https://www.quartic.ai/)

### Inferences
- Kneat's April webinar listed the Validation Expert as roadmap and the 26R2 article presents it as shipped, so it reached release between April and September 2026.
- Basetwo's agent wording appears after May 2026, judging by the change in its press boilerplate.

### Gaps
- Kneat's 26R2 article shows a publication date later than its "last updated" date; exact release date not established.
- Aizon's "early Q1 2026" GA target rests on an aggregator snippet.

## KQ3. What does vendor documentation say about human review, audit trail, e-signatures and validating the AI itself?

### Takeaway
No public product documentation was found; statements come from marketing pages, blogs and one white paper. Five of six say a person reviews AI output (Quartic / ParkourSC says only "guardrails"). None describes an e-signature step specific to AI output. Only ValGenesis and QbDVision describe how the AI itself is qualified.

### Cited Findings
- ValGenesis: prompts and outputs logged with user, date, time; IQ/OQ/PQ; revalidation on any AI component change — [G1](https://www.valgenesis.com/editorial/ensuring-trust-in-ai-the-valgenesis-approach-to-validating-ai-agents-and-functions-for-validation-and-qualification-in-life-sciences)
- QbDVision: AI suggestion kept distinct from the accepted version; opt-in activation; published accuracy metrics — [V1](https://www.qbdvision.com/platform/ai)
- Kneat, Aizon, Basetwo: review or approval stated (advisory findings; approve before publish; drafts "for review"); AI-specific audit trail and validation method not described — [K1](https://kneat.com/webinar/the-kneat-ai-advantage/), [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language), [B3](https://www.basetwo.ai/applications/process-scale-up-and-tech-transfer)

### Inferences
- "Human in the loop" is universal wording; the differentiators are what gets logged (prompt, model version, suggestion versus accepted value) and whether AI findings can block a workflow.

### Gaps
- No source shows an accept / reject screen, an audit-trail entry for an AI action, or admin settings.

## KQ4. Is there independent evidence of real-world use, limitations or criticism?

### Takeaway
Very little. Independent material confirms corporate events and relays vendor interviews; no user review, customer-authored talk or peer-reviewed study of these AI features was found.

### Cited Findings
- Aizon: trade-press feature built on a co-founder interview — [A8](https://www.genengnews.com/topics/artificial-intelligence/smarter-filings-smarter-factories/)
- Quartic: commentary that the release "does not explain which recommendations can trigger automated execution" — [Q3](https://www.remio.ai/post/parkoursc-quartic-acquisition-connects-factory-data-to-the-drug-supply-chain)
- ValGenesis: analyst note is vendor-briefed and predates VAL; pilot outcomes promised for conference talks, none published — [G8](https://axendia.com/blog/2024/12/17/powering-smart-manufacturing-in-life-sciences/), [G10](https://www.valgenesis.com/news/valgenesis-to-bring-real-world-ai-assisted-validation-insights-to-kenx-europe-2026)
- Kneat: management statements via earnings-call coverage — [K6](https://finance.yahoo.com/news/kneat-com-q4-earnings-call-113044763.html). Basetwo: independent coverage is from 2022 and pre-agent — [B7](https://www.genengnews.com/insights/ai-can-make-a-difference-on-the-factory-floor-if-biopharma-invests/)

### Inferences
- The most candid limitation statements come from the vendors themselves (Kneat's webinar page, ValGenesis's LLM knowledge-cutoff disclaimer).

### Gaps
- G2 and Gartner Peer Insights pages returned 403; no review text mentioning AI was seen.

## KQ5. Does any of this AI address technology transfer, scale-up, site-to-site comparison, or assembling evidence across systems?

### Takeaway
Only Basetwo markets an agent for tech transfer and scale-up, and it predicts receiving-site performance from models rather than assembling or comparing transfer evidence. QbDVision's Qurio retrieves and compares knowledge already structured inside QbDVision. The validation vendors work within their own document sets.

### Cited Findings
- Basetwo: "Predict process performance at a new scale or site before you run it"; "Each site has its own model fitted to its specific data."; sites compared on CQAs, CPPs and fitted model parameters; transfer package drafted from historian, MES, LIMS and SOP inputs — [B3](https://www.basetwo.ai/applications/process-scale-up-and-tech-transfer)
- QbDVision: Qurio to "Accelerate technology transfer": "Surface historical parameters, qualified materials, suppliers, and control strategies from previous programs." — [V1](https://www.qbdvision.com/platform/ai)
- Aizon: Unify offers "Batch Comparison Analytics"; Agentic Studio reads data already on the Aizon platform — [A1](https://www.aizon.ai/), [A4](https://www.aizon.ai/blog/introducing-aizon-agentic-studio-your-production-data-now-speaking-your-language)
- Quartic: PD Optimizer, "In-silico optimization for faster product scale-up." — [Q4](https://www.quartic.ai/)
- ValGenesis VAL "Compare" (change impact) and Kneat's Summary Agent (across workspaces) operate on validation content inside their own platforms — [G5](https://www.valgenesis.com/smart-gxp/ai-native-gxp-validation), [K2](https://kneat.com/?p=16587)

### Inferences
- "Across systems" in every case means data previously ingested into the vendor's own platform; no source describes an agent querying several live source systems or using connectors such as MCP.
- No vendor claims an AI that issues a transfer-readiness verdict with evidence attached.

### Gaps
- Whether Basetwo's draft transfer package is a shipped output or a demo illustration.

## Summary table
| Vendor | Where AI lives | What it does | Approval model | Status / date | Evidence quality |
|---|---|---|---|---|---|
| Quartic.ai | Modelling workbench and monitoring apps; no assistant found | Predictive / multivariate models, rule-based decisions; parent claims it "prescribes" within guardrails | Not described | Acquired by ParkourSC 14 Oct 2026; no generative AI found | LOW |
| Aizon | Agentic Studio, a prompt-to-dashboard builder | Generates apps, dashboards, draft APQR from platform data | User approves before publish; agent "never publishes autonomously" | Introduced 19 Feb 2026; no GA wording; no acquisition found | LOW-MEDIUM |
| Basetwo | Agent in modelling workbench | Marketed: data prep, hybrid model, simulation, draft transfer package. Research: MPC writes setpoints | Drafts "for review"; no gate described | Marketed Nov 2026, undated; closed loop is research; no acquisition found | LOW |
| QbDVision | Qurio Q&A and PDF import inside the platform | Cited answers, comparisons, PDF-to-record suggestions | User accepts suggestion; opt-in activation; credibility plans | "Launching" Aug 2026; no GA date; no acquisition found | LOW-MEDIUM |
| ValGenesis | VAL embedded in the validation suite | Drafts protocols, gap checks, evidence verification, anomaly flags | Human review of every key output; prompt / output audit log; IQ/OQ/PQ | VAL 1.0 activatable per Oct 2025 white paper; next generation in limited pilot Apr 2026; no GA announcement | LOW-MEDIUM |
| Kneat | Inside Kneat Gx on documents, plus chatbot | Advisory review flags, regulatory Q&A, summary sections written into draft documents | SME review; advisory only; admin enablement | Review Assistant released by Apr 2026; 26R2 adds Validation Expert and Summary Agent; private under Thoma Bravo since 11 Aug 2026 | LOW-MEDIUM |

## Could not establish
- Help-centre, release-note or admin documentation for any vendor's AI features (none public; Basetwo docs gated).
- Quartic generative AI, copilot or agent features: no public evidence found. Queries: "Quartic.ai AI agents generative AI pharma manufacturing 2026"; "ParkourSC acquires Quartic press release October 2026 manufacturing AI agents"; `Quartic "eXponence" OR "iLuminator" copilot OR "generative AI" OR "LLM" OR "agent"`.
- AI in ValGenesis iRisk, iCPV or Process Manager beyond ML and multivariate analytics: no public evidence found. Query: "ValGenesis iCPV Process Manager AI assistant process insights iRisk AI risk assessment". Whether iRisk survives as a product name: not established.
- GA dates for Aizon Agentic Studio, QbDVision Qurio, Basetwo agents, ValGenesis VAL: no public evidence found. Queries: "Aizon agentic AI platform announcement October 2025 press release"; "QbDVision Qurio launch AI assistant CMC announcement"; "Basetwo AI agents launch agentic tech transfer scale-up platform announcement 2026"; "ValGenesis next generation VAL INTERPHEX 2026 press release AI agents".
- Independent pilot results, criticism or user reviews of any AI feature: no public evidence found. Queries: "ValGenesis VAL review OR criticism OR pilot results -site:valgenesis.com"; "Kneat Gx reviews G2 OR Gartner Peer Insights 2026 AI".
- Kneat annual report / MD&A text on AI: investor pages returned 403. Kneat is no longer TSX-listed.
- LLM provider for Aizon, Basetwo, ValGenesis, Kneat; e-signature treatment of AI output at any vendor; AI pricing.
- Not run (session web-search budget exhausted): searches for VAL demo recordings and for Quartic 2025-26 generative-AI announcements.
