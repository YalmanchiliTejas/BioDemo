# Competitor AI agents: lab, R&D-data and bioprocess-data vendors — evidence file (as of 2026-11-16)

**Key.** VC vendor claim · VD vendor documentation · IND independently evidenced · F fetched and read · S search snippet only · n.d. undated. Quotes are verbatim as returned by the page reader. Benchling Help Center pages block automated fetch; each was read through the public help-centre JSON endpoint for the same article ID and is cited by its public URL. Item (d), release status and dates, is in the KQ2 table.

## KQ1. Autonomous multi-step agents, or prompt-in / draft-out assistants? (per-vendor records)

### Takeaway
Only Benchling documents agents that run unattended on schedules or record events (Preview, mid-2026) and that can write without per-action approval in "Full actions" mode. Everything else found is user-initiated: in-session plan-and-execute chat (Dotmatics, Sapio, Invert) or builder assistants with approval gates (TetraScience). No shipped own-brand agent was found for IDBS or, after acquisition, Ganymede.

### Cited Findings

#### 1. Benchling — (f) STRONG on behaviour (dated help-centre docs); WEAK on independent use

Sources: [B1] launch release · VC/F · 2025-10-07; [B3] GA blog · VC/F · 2026-02-10; [B4] MCP connectors release · VC/F · 2026-04-16; [B5] AI chat · VD/F · upd. 2026-09-03; [B6] Deep Research · VD/F · upd. 2026-10-22; [B7] Compose · VD/F · upd. 2026-08-26; [B8] Data Entry · VD/F · upd. 2026-09-03; [B9] Agent Modes · VD/F · 2026-08-22; [B10] Agents (Preview) · VD/F · upd. 2026-10-15; [B11] What's New Jul–Aug 2026 · VD/F · 2026-09-29; [B12] What's New Oct 2026 · VD/F · 2026-11-03; [B13] Release Notes Vol. 9 · VD/F · 2026-11-02; [B14] AI data protection · VD/F · upd. 2026-07-31; [B16] Validated Cloud patches · VD/F · upd. 2026-02-09; [B17] Slack app (Preview) · VD/F · upd. 2026-08-20; [B18] ZenML summary of a Benchling talk · VC/F · 2026; [B20] G2 · IND/S · n.d.; [B21] Bioprocess guide · VD/F · upd. 2026-07-22

[B1]: https://www.benchling.com/news/introducing-benchling-ai
[B3]: https://www.benchling.com/blog/benchling-ai-now-generally-available
[B4]: https://www.benchling.com/news/benchling-launches-ai-connectors-to-power-data-ecosystem
[B5]: https://help.benchling.com/hc/en-us/articles/45766024411405-Use-Benchling-AI-chat
[B6]: https://help.benchling.com/hc/en-us/articles/38679507502733
[B7]: https://help.benchling.com/hc/en-us/articles/39437880024717-Create-entries-and-templates-with-the-Compose-Agent
[B8]: https://help.benchling.com/hc/en-us/articles/34900709662989-Automate-manual-data-entry-in-structured-tables-with-the-Data-Entry-agent
[B9]: https://help.benchling.com/hc/en-us/articles/48328875643533-Agent-Modes-and-Approvals
[B10]: https://help.benchling.com/hc/en-us/articles/47709160672781-Setting-up-and-Using-Benchling-Agents-Preview
[B11]: https://help.benchling.com/hc/en-us/articles/49261371214733-What-s-New-in-Benchling-July-August-2026
[B12]: https://help.benchling.com/hc/en-us/articles/50095748469901-What-s-New-in-Benchling-October-2026
[B13]: https://help.benchling.com/hc/en-us/articles/50086670312077-Release-Notes-Volume-9-2026
[B14]: https://help.benchling.com/hc/en-us/articles/20901323667853-Data-protection-and-security-for-AI-at-Benchling
[B16]: https://help.benchling.com/hc/en-us/articles/34548660058509-2025-Benchling-Validated-Cloud-Maintenance-Releases
[B17]: https://help.benchling.com/hc/en-us/articles/46837058375437-Setting-up-Benchling-AI-for-Slack-Preview
[B18]: https://www.zenml.io/llmops-database/ai-agents-for-life-sciences-rd-accelerating-drug-discovery-with-context-rich-data
[B20]: https://www.g2.com/products/Benchling/reviews
[B21]: https://help.benchling.com/hc/en-us/articles/39279130261133-How-to-Use-Benchling-Bioprocess

- **(a) Where.** Global chat: "Click the AI icon in the navigation bar"; entry-scoped "Edit contents" chat [B5]; Compose side panel [B7]; Data Entry modal from a table header [B8]; triggered Agents "configured via Chat or manually via a form" [B10]; Science Foundries, "shared workspaces where a team of agents collaborates with a team of scientists" [B12]; outside assistants: "Benchling now exposes its AI agents through the Model Context Protocol (MCP)" [B11].
- **(b) Does.** Drafts entries, templates and cited reports [B7][B6]; fills result, registration and plate tables [B8]; builds dashboards and Automation templates from chat [B11][B12]; reads external tools through admin-configured MCP connectors [B4].
  - Proposes: "Default mode does not allow an agent to make changes directly to Benchling objects." [B9]
  - Writes: "Full actions mode lets an agent take any action you're personally permitted to take in Benchling" [B9].
  - Unattended: "Once set up, an agent runs automatically based on its trigger" — time-based or event-based (e.g. Study, Entry, Run, File, Workflow Task); cap of "up to 20 automated agent runs per rolling 10-minute window" [B10].
- **(c) Approval.** "Once you're in Full actions mode, most actions happen without further approval." "The exception is admin-level actions, such as creating or editing schemas." [B9] Triggered agents are given a mode at set-up: "In Default, the agent can research and draft, but will ask for approval before editing Benchling objects." [B10] Data Entry previews, then "Approve and insert rows" [B8]. "Benchling AI cannot submit tables at this time." [B5]
  - Audit: "All actions an agent takes are captured in Benchling's audit log and version history, just like actions you take yourself." [B9] "Reviewers can distinguish between changes a user made directly and changes a user made via Chat." [B5]
  - Admin: "Admins can turn Full actions mode on or off for individual users." [B9]; agents with their own permissions "must be approved by admins before agents gain any data access" [B10].
  - Tension: [B14] says "Any AI capability that can write data, or perform actions, in Benchling requires the user to accept the output or action".
  - GxP: "Benchling AI for Slack is not supported on Validated Cloud tenants." [B17] A Validated Cloud patch note reads "Only customers using the Deep Research AI Agent are impacted." [B16] Nothing found on validated use of Agents or Full actions.
- **(e) Beyond claims.** A vendor talk concedes "many scientific tasks resist standardized evaluation" [B18]. G2: 4.5/5 from 65 reviews; sampled complaints not about AI [B20]. No independent evaluation or customer-authored account found.

#### 2. Sapio Sciences (ELaiN / Elain) — (f) WEAK–MODERATE: claims plus one briefing-based analyst note; no public docs

Sources: [S1] Sapio blog · VC/F · 2024-01-26; [S2] SelectScience release reprint · VC/F · 2024-09-05; [S3] Sapio release · VC/F · 2025-09-16; [S4] Axendia analyst note (vendor briefing) · IND/F · 2025-10-09; [S5] IPT Online release reprint · VC/F · 2026-01-13; [S6] Sapio release via BioPharma Dive · VC/F · 2026-04-29; [S9] IntuitionLabs consultancy · IND/S · n.d.; [S10] G2 Sapio ELN · IND/S · n.d.

[S1]: https://www.sapiosciences.com/blog/sapio-elain-your-science-aware-ai-lab-assistant/
[S2]: https://www.selectscience.net/article/sapio-sciences-advances-its-ai-powered-lab-assistant
[S3]: https://www.sapiosciences.com/news/sapio-sciences-introduces-worlds-first-3rd-generation-eln/
[S4]: https://axendia.com/blog/2025/10/09/sapio-introduces-the-electronic-notebook-that-thinks-like-a-scientist/
[S5]: https://www.iptonline.com/articles/sapio-sciences-announces-partner-ecosystem-for-elain-its-thirdgeneration-ai-lab-notebook
[S6]: https://www.biopharmadive.com/press-release/20260429-sapio-sciences-brings-claude-cowork-to-the-lab/
[S9]: https://intuitionlabs.ai/services/sapio-sciences/ai-integration
[S10]: https://www.g2.com/products/sapio-eln/reviews

- **(a) Where.** "open the chat and notifications widget in the top left corner" [S1]; prompts "in text or voice" [S2]; inside ELN experiments [S3]; from Claude Cowork, Copilot or ChatGPT through Elain [S6].
- **(b) Does.** "Sapio ELaiN can take actions both within the system and with external agents." [S2] "Sapio ELaiN can transform a document-based SOP into a structured experiment within minutes." [S4] Science tools (docking, codon optimisation) and partner apps run from the prompt [S3][S5]. Over MCP, "Claude Cowork can also take actions on the user's behalf to operate on ELN experiments or LIMS processes and data", e.g. "Register compounds directly into the Sapio Platform from an SDF file" [S6]. Writes to the system of record, per vendor.
- **(c) Approval.** No confirmation or approval step is described in any source read. Claims: "Sapio Elain captures every action with full provenance" [S3]; "all actions are executed with full traceability with attribution to the requesting user." [S6]
- **(d) Note.** Packaging conflict: "optional paid-for feature in the future" [S1] versus "Sapio Elain is not an add-on." [S3]
- **(e) Beyond claims.** The analyst note rests on a vendor briefing, with no hands-on test or criticism [S4]. G2: "This product hasn't been reviewed yet!" [S10]. A consultancy says Sapio "does not currently ship a native MCP server" [S9], against [S6]'s "built on the Model Context Protocol (MCP)". No public documentation found.

#### 3. Dotmatics (Siemens) — Luma Agent — (f) WEAK–MODERATE: claims, analyst note, bylined trade piece; no docs

Sources: [D1] release · VC/F · 2026-05-13; [D2] Dotmatics blog · VC/F · 2026-05-12; [D3] Lab Manager, bylined, relays vendor statements · VC/F · n.d.; [D4] Axendia note (vendor briefing) · IND/F · 2026-05-19; [D6] PharmTech · IND/F · 2025-07-01

[D1]: https://www.dotmatics.com/news/introducing-luma-agent
[D2]: https://www.dotmatics.com/blog/luma-agent-your-ai-co-scientist
[D3]: https://www.labmanager.com/dotmatics-launches-luma-agent-an-ai-co-scientist-built-on-structured-scientific-data-35374
[D4]: https://axendia.com/blog/2026/05/19/bridging-scientific-intelligence-across-the-product-and-process-lifecycle/
[D6]: https://www.pharmtech.com/view/siemens-finalizes-dotmatics-acquisition

- **(a) Where.** "a new agentic AI capability embedded in the Luma Scientific Intelligence Platform" [D1]; UI placement unspecified. Also "MCP-enabled and can be surfaced within tools like Claude" [D4].
- **(b) Does.** "The agent builds a plan, works through it step by step, and comes back with something complete." [D2] Reports, workflows and configuration: "describe a schema or a data flow in plain language and the agent configures it"; external models connected over MCP can configure Luma, which "executes those changes directly in Luma" [D1]. Prompt-initiated; no scheduled or event trigger described.
- **(c) Approval.** "Every write operation requires explicit human approval before it executes. Every step the agent takes is logged and auditable." [D2] Approval UI, signatures and validated use are undocumented.
- **(d) Note.** Ownership: Siemens completed "its $5.1 billion acquisition of Boston-based Dotmatics", now under "Siemens' Digital Industries Software division" [D6].
- **(e) Beyond claims.** The analyst quotes the president — the assistant will "eventually operate with greater autonomy" — and the CPO: "The biggest challenge is governance." [D4] Editor's note: "the governance architecture may matter as much as the feature set." [D3] No docs, reviews or customer talks found.

#### 4. IDBS (Polar) — (f) WEAK; what exists points to no shipped own-brand agent

Sources: [I1] SelectScience, vendor year-in-review · VC/F · 2025-12-17; [I2] IDBS AI page · VC/F · n.d.; [I3] SelectScience, Alchemi partnership · VC/F · 2026-06-16; [I4] Polar Insight page · VC/F · n.d.; [I5] SelectScience, Polar Control · VC/F · 2025-03-07; [I6] Polar BioProcess page · VC/F · n.d.

[I1]: https://www.selectscience.net/article/idbs-celebrates-customer-successes-and-product-innovations-in-2025
[I2]: https://www.idbs.com/polar/ai-data-foundations/
[I3]: https://www.selectscience.net/article/idbs-and-alchemi-partner-to-accelerate-biopharma-regulatory-filings-with-compliant-ai-agents
[I4]: https://www.idbs.com/polar/insight/
[I5]: https://www.selectscience.net/article/idbs-unveils-idbs-polar-control-revolutionizing-process-management-in-biopharmaceutical-development
[I6]: https://www.idbs.com/polar/bioprocess/

- **(a)(b)** 2025 AI: "summarizing scientific papers" and "natural-language semantic search"; agentic work "currently in proof-of-concept" [I1]. The AI page footnotes "products and features that are currently under development and are not currently available" [I2]. The Polar BioProcess page describes no AI feature [I6]. Partner route: "Alchemi's agents draw on Polar's governed data to draft these reports and dossiers" [I3].
- **(c)** Partner drafts are "routed through human-in-the-loop workflows for review and sign-off"; "Each human and AI action is captured in a 21 CFR Part 11 audit trail" [I3].
- **(e)** Nothing beyond vendor and partner announcements.

#### 5. TetraScience — (f) MODERATE for builder assistants (versioned docs); WEAK for "agentic" claims

Sources: [T1] What is Tetra AI? · VD/F · upd. 2026-05-15; [T2] AI Features · VD/F · n.d.; [T3] Workflow Creation Assistant release notes · VD/F · 2026-05-21; [T4] Tetra Data Assistant · VD/F · 2026-10-21; [T4b] its user guide v1.1.x · VD/F · n.d.; [T5] MCP server · VD/F · n.d.; [T5b] its beta release notes · VD/F · upd. 2026-10-22; [T6] AI Services · VD/F · upd. 2026-10-21; [T8] Databricks partner blog · VC/F · 2026-03-16; [T9] Use Case Factory · VD/F · n.d.

[T1]: https://developers.tetrascience.com/docs/what-is-tetra-ai
[T2]: https://developers.tetrascience.com/docs/ai-features.md
[T3]: https://developers.tetrascience.com/docs/workflow-creation-assistant-v10x.md
[T4]: https://developers.tetrascience.com/docs/tetra-data-assistant.md
[T4b]: https://developers.tetrascience.com/docs/tetra-data-assistant-user-guide-v11x.md
[T5]: https://developers.tetrascience.com/docs/tetra-data-assistant-mcp-server.md
[T5b]: https://developers.tetrascience.com/docs/tetra-data-assistant-mcp-server-beta-release-notes.md
[T6]: https://developers.tetrascience.com/docs/tetrascience-ai-services.md
[T8]: https://www.databricks.com/blog/how-tetrascience-accelerates-biopharma-production-ready-data-and-scientific-intelligence
[T9]: https://developers.tetrascience.com/docs/what-is-the-scientific-use-case-factory.md

- **(a) Where.** Platform apps: Tetra Data Assistant (tabs plus "an interactive chat sidebar") [T4]; Workflow Creation Assistant, Visual Pipeline Builder ("Conversational AI interface for building pipelines") and Review by Exception Assistant [T2]; an MCP server for coding assistants such as Claude Code, Cursor and GitHub Copilot [T5].
- **(b) Does.** Generates schema, parser, protocol and README, then will "publish all three artifacts to the TDP" [T4b]. Generates pipeline code but "won't configure pipeline triggers" [T3]. Review by Exception: "AI models trained on customer-specific golden batches analyze chromatogram profiles and flag deviations." [T8] Concept page: "Tetra AI provides semi-autonomous and fully autonomous agentic capabilities" [T1]; no documented product behaviour behind that phrase was found.
- **(c) Approval.** Staged buttons: Approve IDS, Approve Task Script, Approve Protocol, Approve Documentation, then Deploy Artifacts [T4b]. "AI-generated code and artifacts must always be reviewed for accuracy, data integrity, and security before use." [T5b] Admins choose AI-workflow versions "made available for use in production" [T6]. No GxP statement in the AI docs read.
- **(e) Beyond claims.** Partner blog: one application "deployed in production at a top-20 pharma"; no customer named [T8]. No independent evidence found.

#### 6. Ganymede (acquired by Apprentice.io) — (f) WEAK: alpha announcement only; docs show a code-generation helper

Sources: [G1] Business Wire release via FinancialContent · VC/F · 2025-08-06; [G2] acquisition release · VC/F · 2026-01-21; [G3] docs, AI Help and Code Generation · VD/F · n.d.; [G4] docs home · VD/F · n.d.; [G6] Apprentice product page · VC/F · n.d.; [G7] ganymede.bio · VC/F · n.d.

[G1]: https://www.financialcontent.com/article/bizwire-2025-8-6-ganymede-launches-scientific-ai-agent-platform-to-accelerate-process-development-r-and-d-and-manufacturing
[G2]: https://www.newswire.com/news/apprentice-io-acquires-ganymede-to-deliver-the-industrys-first-ai-native
[G3]: https://docs.ganymede.bio/sdk/AI
[G4]: https://docs.ganymede.bio/
[G6]: https://apprentice.io/product/ganymede
[G7]: https://www.ganymede.bio/

- **(a)(b)** Announced: "the first secure, deterministic AI agents purpose-built for science, engineering, and hard tech industries"; workflows "from ELN/LIMS triggers to reagent ordering, using AI decisioning" [G1]. Documented: "Ganymede incorporates OpenAI models to facilitate document search and code generation in Flow development."; the user pastes generated code in [G3]. The docs' "Agents" are "locally installed executables for delivering data to and acquiring data from lab instruments" [G4].
- **(c)** Claimed "role-based permissions, and auditability" [G1]; no approval model described.
- **(d) Note.** After acquisition: "The full suite of Ganymede products for R&D and diagnostics data will continue to be offered." [G2] Current pages list "AI-powered modules for curve fitting, qPCR, chromatography, and more, without any code" [G6] and no agent product [G7].
- **(e)** None independent.

#### 7. Invert (Invert Assist) — (f) WEAK–MODERATE: marketing only; a third-party profile flags unverified claims

Sources: [V1] PR Newswire · VC/F · 2025-10-28; [V2] Assist page · VC/F · n.d.; [V3] Intelligence page · VC/F · n.d.; [V4] compliance page · VC/F · n.d.; [V6] Healthcare Discovery profile (independence undisclosed) · IND/F · upd. 2026-09-29

[V1]: https://www.prnewswire.com/news-releases/invert-launches-invert-assist-an-ai-powered-analysis-interface-built-for-bioprocess-302596033.html
[V2]: https://www.invertbio.com/assist
[V3]: https://www.invertbio.com/product/intelligence
[V4]: https://www.invertbio.com/compliance
[V6]: https://healthcarediscovery.ai/companies/invert/

- **(a) Where.** "Using a simple chat interface, users can direct Invert Assist to detect trends and correlations" [V1]; chat panel with "Save as Skill" and an "Assist flagged" proactive panel [V3].
- **(b) Does.** It "finds the right runs, loads the data, chooses the right analysis" [V2]; models, forecasts, reports and reusable Skills [V3]. Proactive: "live run surveillance against your historical baselines"; Assist "drafts the investigation — ready for your team to review, refine, and file" [V3]. Write-back to other systems is not stated.
- **(c) Approval.** Drafts are for review [V3]; method is exposed by "executing fully accessible Python code for traceable, verifiable results" [V1]; "Generated code runs in isolated environments with no direct access to live production databases or infrastructure." [V4] Nothing on validated use of Assist.
- **(e) Beyond claims.** Profile: "Those evaluations are internal, and no outside party has published a check on them."; named customers: "None, anywhere." [V6] The public trial runs on synthetic data [V2].

### Inferences
- "Agent" covers three interaction models here: triggered background runs (Benchling, Preview); in-session plan-and-execute chat (Benchling, Dotmatics, Sapio, Invert); generators with deploy gates (TetraScience, Ganymede's helper).
- Benchling's mode-switch approval appears to count as the acceptance [B14] requires, or [B14] predates Agent Modes.
- [B16] implies Deep Research ran on Validated Cloud tenants by late 2025.

### Gaps
- [B10] does not say how approval prompts surface during unattended runs.
- No evidence either way on scheduled or event triggers for Sapio or Dotmatics.

## KQ2. What is generally available versus announced, beta or roadmap?

### Takeaway
GA is explicit for Benchling AI, Sapio ELaiN and TetraScience's Workflow Creation Assistant. Dotmatics says "now available" but enables per instance. Benchling's triggered Agents and Science Foundries are Preview. IDBS's agentic work and Ganymede's agents did not pass proof of concept or alpha in public sources.

### Cited Findings
| Vendor · feature | Status (source wording) | Date | Source |
|---|---|---|---|
| Benchling AI (chat, Deep Research, Compose, Data Entry) | Launched; then "Benchling AI is now generally available." | 2025-10-07; 2026-02-10 | [B1][B3] |
| Benchling MCP Server | "available now following a beta period" | 2026-04-16 | [B4] |
| Benchling Full actions mode | Released, no label | Jul–Aug 2026 | [B11] |
| Benchling triggered Agents; Science Foundries | "(Preview)"; "currently in Preview", tagged "[Open LA]" | from 2026-07-28; Oct 2026 | [B10][B12][B13] |
| Sapio ELaiN | "now generally available after a successful beta launch in November 2023" | 2024-09-05 | [S2] |
| Sapio third-generation ELN; Claude Cowork link | Launched; "now integrated" | 2025-09-16; 2026-04-29 | [S3][S6] |
| Dotmatics Luma Agent | "Luma Agent is now available."; enabled through "your Dotmatics account manager" | 2026-05-12 | [D2] |
| IDBS agentic AI; Alchemi agents | "currently in proof-of-concept"; availability unstated | 2025-12-17; 2026-06-16 | [I1][I3] |
| TetraScience Workflow Creation Assistant | v1.0.0, "its first general availability version" | 2026-01-09 | [T3] |
| TetraScience MCP server | v0.5.0, "the first publicly available beta version" | 2026-04 | [T5b] |
| Ganymede agent platform | "currently in its Alpha stage"; company acquired 2026-01-21 | 2025-08-06 | [G1][G2] |
| Invert Assist | Launched; no GA or version wording | 2025-10-28 | [V1] |

### Inferences
- "[Open LA]" probably means open limited availability; the release notes do not define it.

### Gaps
- Status of TetraScience's Tetra Data Assistant, Visual Pipeline Builder and Review by Exception Assistant; whether Ganymede's agents survived the acquisition.

## KQ3. What does documentation say about human review, audit trail, signatures and GxP use?

### Takeaway
Only Benchling and TetraScience publish documentation of review and audit mechanics. None of the seven documents GxP-validated use of its AI agents or electronic signature of AI output; for the other five the only statements are marketing.

### Cited Findings
- Benchling documents mode-based approvals, per-plan approval of admin-level actions, and AI edits distinguishable in audit log and version history [B9][B5]; "Changes to AI settings in the Tenant Admin Console are also audited" [B14].
- TetraScience documents staged Approve steps, a mandatory-review warning and admin gating of production versions [T4b][T5b][T6].
- Context: "the validation obligation cannot be delegated to the vendor." — [Lab Manager](https://www.labmanager.com/ai-in-regulated-labs-what-counts-as-a-validated-system-35645) (IND/F, n.d.).

### Inferences
- Benchling's attribution of AI writes to the initiating user, flagged as AI-made, is the only documented audit treatment in this set.

### Gaps
- Signature handling of AI-made changes: no documentation found for any vendor.

## KQ4. Is there independent evidence of real-world use, limitations or criticism?

### Takeaway
Very little: two briefing-based Axendia notes, one bylined Lab Manager piece and one third-party profile. No user review of any AI feature and no customer-authored account was found.

### Cited Findings
- Analyst notes rest on vendor briefings, with no hands-on evaluation [S4][D4].
- Trade press mostly reprints releases [S2][S5][I1][I3]; [D3] adds an independent editor's note.
- User reviews: Sapio ELN has none [S10]; Benchling's sampled G2 complaints are not about AI [B20].
- Criticism: Invert's performance claims are unverified and no customer is named [V6]; Dotmatics' CPO names governance as the main challenge [D4]; Benchling's speaker concedes evaluation limits [B18].
- Named users appear only in vendor claims, e.g. a Harvard Medical School lab [B1].

### Inferences
- Documented behaviour can be stated for Benchling and TetraScience; independent proof of outcomes cannot be cited for any of the seven.

### Gaps
- Reddit, Gartner Peer Insights, Endpoints, STAT and Fierce were not checked: the session's web-search budget ran out.

## KQ5. Does any of this AI address tech transfer, scale comparison, site-to-site comparison or cross-system evidence assembly?

### Takeaway
No vendor documents an AI agent built for technology transfer or site-to-site process comparison. The nearest items are Invert's demo content, IDBS's non-generative cross-scale analytics, a Dotmatics–Siemens capability described as potential, and cross-system retrieval through MCP connectors.

### Cited Findings
- Invert: Assist example "Target: identify feed strategy for 200L tech transfer."; "Historical comparators across Ambr250, Pilot 50L, GMP 2,000L." [V2] (demo content).
- IDBS: "Track and compare seed train performance across scales to support data-driven scale-up decisions" [I4]; Polar Control "streamlines technology transfer by offering a clear and detailed record of process parameters" [I5]. Neither is described as generative or agentic.
- Dotmatics–Siemens: integration "creates the potential for bi-directional data flow between research and manufacturing"; "Three Lighthouse customers are actively co-developing this capability with Dotmatics today." [D4]
- Ganymede/Apprentice: "Ganymede makes R&D connectivity programmable, so tech transfer doesn't require starting over." [G2]; not tied to an agent.
- Benchling: "Bioprocess simplifies tech transfer, improves efficiency, and unlocks downstream data science and ML insights." [B21]; no AI feature for it described. Cross-system: the MCP Client "connects to any tool with an existing MCP server" [B4].
- IDBS–Alchemi: partner agents assemble regulatory drafts from Polar data [I3].
- TetraScience: listed use cases include deviation detection and yield prediction, none on tech transfer [T9].
- Sapio: none found.

### Inferences
- In every vendor read, tech transfer appears as positioning rather than as a documented AI workflow.

### Gaps
- Whether Invert's tech-transfer examples reflect customer use or synthetic demo data is not stated.

## Summary table and could-not-establish items

| Vendor | Where AI lives | What it does | Approval model | Status / date | Evidence quality |
|---|---|---|---|---|---|
| Benchling | Global and entry-scoped chat; table modal; triggered Agents; Science Foundries; MCP | Drafts entries and reports; in Full actions writes records and schemas; schedule- or event-triggered runs | Default proposes; Full actions writes without per-action approval except admin-level; AI edits flagged in audit log | GA 2026-02-10; Agents and Foundries in Preview | Strong on behaviour; weak independent |
| Sapio | Chat widget in ELN/LIMS; external assistants over MCP | Builds experiments from prompts or SOPs; runs science tools; acts on records | None described; actions attributed and recorded (claims) | GA 2024-09; Claude Cowork 2026-04-29 | Weak–moderate |
| Dotmatics (Siemens) | Embedded in Luma; external assistants over MCP | Plans and executes analyses, reports and platform configuration | Explicit approval before every write; logged steps (claims) | "Now available" 2026-05-12, enabled per instance | Weak–moderate |
| IDBS | Nothing shipped under own brand; partner agents read Polar data | Partner agents draft regulatory documents | Human review and sign-off; Part 11 audit trail (partner claim) | Proof of concept 2025-12; partnership 2026-06-16 | Weak |
| TetraScience | Platform apps with chat sidebar; MCP server for coding tools | Generates and deploys schemas, parsers and pipeline code; flags chromatography exceptions | Staged Approve buttons; mandatory-review warning; admin gating | One assistant GA 2026-01-09; MCP beta 2026-04 | Moderate docs; weak on "agentic" |
| Ganymede (Apprentice.io) | Notebook code-generation helper; chat agents announced | Documented: code and doc help. Claimed: QC flagging, reports, triggered workflows | Not described | Alpha 2025-08-06; acquired 2026-01-21 | Weak |
| Invert | Chat panel plus proactive "Assist flagged" panel | Analyses and models via visible Python; drafts investigations and reports | Drafts for review; sandboxed code (claims) | Launched 2025-10-28 | Weak–moderate |

**Could not establish**
1. Benchling: how approvals work in unattended runs; validated-use position on Agents, Full actions and Foundries; Benchtalk 2026 launch details (15 October 2026, five Foundry agents, Parabilis as user), seen only in a search summary whose source page was not identified.
2. Sapio: any public documentation; whether actions need confirmation; whether the MCP server is native. The ELaiN whitepaper PDF was image-only and unreadable.
3. Dotmatics: documentation, approval UI, MCP tool scope, Lighthouse customer names.
4. IDBS: any shipped own-brand assistant; availability of the Alchemi integration.
5. TetraScience: what "fully autonomous agentic capabilities" refers to; any chat assistant over scientific data for scientists.
6. Ganymede: whether the agent platform reached beta or GA.
7. Invert: documentation, write-back behaviour, named customers.

**No public evidence found — queries tried**
- Sapio: `Sapio ELaiN help documentation release notes agent approve`; `Sapio ELaiN user review G2 OR reddit`; help.sapiosciences.com does not resolve.
- Dotmatics: `Dotmatics "Luma Agent" documentation OR "release notes" approval audit MCP server`.
- IDBS: `IDBS Polar AI copilot assistant BioProcess`; `IDBS Polar agentic AI 2026 assistant launch`; `IDBS i3 2026 agentic AI Polar "Lab Loop"`.
- TetraScience: `TetraScience 2026 AI agents launch "Tetra AI" assistants`; `TetraScience "Tetra AI" chat agents GxP documentation`.
- Ganymede: `docs.ganymede.bio AI agents natural language flows`; `Apprentice.io Ganymede AI agents 2026 beta`.
- Invert: `Invert Assist 2026 agents tech transfer scale-up comparison`; `Invert "Assist" Skills proactive monitoring blog 2026`.
- Benchling: `Benchling AI agents review reddit OR "G2" OR Endpoints OR STAT limitations 2026`.
- Not run (budget exhausted): Science Foundries press coverage; Benchling launch coverage in Fierce, Endpoints or STAT; independent reviews of Luma Agent.
