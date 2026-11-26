# Tech transfer and process comparison: tools and practice (as of 2026-11-16)

Legend: **F** = FETCHED (opened and read); **S** = SNIPPET (search result only). **VC** vendor claim, **VD** vendor documentation. PDF quotes (WHO, PDA/ISPE contents pages, ICH, Veeva, IPM) were read directly; web-page quotes came through the fetch tool's extractor, so spot-check before publishing.

## 1. What must a gap assessment and a facility-fit assessment contain, who owns them, and at which stage? What is the standard structure and document set?

### Takeaway
WHO TRS 1044 Annex 4 (2022) is the only freely readable guidance. It puts due diligence and gap analysis first, assigns them to a joint qualified team with both quality units, and requires the transfer protocol to carry a parallel SU-vs-RU comparison. PDA TR 65 and the ISPE guide are paywalled; only their contents pages were read. "Facility fit" is practitioner language, not a WHO term.

### Cited Findings
**Stages**

| Source | Stages |
|---|---|
| [WHO TRS 1044 Annex 4, 2022, §12.1 · F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf) | Project initiation; project planning; project transfer execution; project review and close-out |
| [PDA TR 65, Revised 2022, contents · F](https://store.pda.org/TableOfContents/TR65TOC.pdf) | "The Six-Stage Technology Transfer Process": Initiation, Planning, Knowledge Transfer, Readiness, Execution, Handover. Each has workstreams Business, Project Manager, Process, Analytical, Engineering, Manufacturing, Regulatory, Quality, Sourcing/Supply Chain |
| [ISPE GPG Technology Transfer, 3rd ed., ©2018, contents · F](https://ispewebassets.org/files/publications/guidance-documents/ISPE-GPG1-TT3_TOC.pdf) | "Form Transfer Team and Develop Charter"; "Consolidate Knowledge for Transfer and Develop Technology Transfer Proposal"; "Identify Risks, Conduct Risk Assessments, and Develop Technology Transfer Plan"; "Operational Readiness"; "Process (Procedure) Qualification"; "Finalize Transfer and Perform Review" |
| [ICH Q10, 2008, §3.1.2 · F](https://database.ich.org/sites/default/files/Q10%20Guideline.pdf) | Goal only: "to transfer product and process knowledge between development and manufacturing, and within or between manufacturing sites" |

**Gap analysis — WHO Annex 4 ([F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf))**
- Definition: "The identification of the critical elements of a process that are available at the sending unit (SU) but are missing from the receiving unit (RU) with the objective of assessing which gaps have a potential impact on the process or method and to mitigate those gaps".
- Stage: "the first steps should include a process of due diligence and gap analysis through visits to the SU and RU" (§4.1), before the transfer starts (§4.2). Repeated in planning: "The team should perform a gap analysis and risk assessment" (§12.8). In execution "the RU should identify any differences in facilities, systems and capabilities and discuss these with the SU" (§12.20).
- Owner: "a team of appropriately qualified persons ... It is recommended that the quality units of the SU and RU participate" (§4.3); "The SU should assess the suitability and degree of preparedness of the RU before transfer" (§5.12); the team is formed jointly by marketing authorization holder, SU and RU (§12.7).
- Contents: "personnel, premises, equipment and instruments, utilities, cleaning, quality control, documentation, computerized systems, qualification, validation, and further health, safety and environment-related considerations" (§4.4); feasibility "may include technical, engineering, business, quality, regulatory, supply and legal aspects" (§4.5).

**Facility and equipment fit — WHO Annex 4 ([F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf))**
- "A review and side-by-side comparison of the equipment and instruments, as well as process steps and parameters of the SU and RU, should be carried out in terms of their working principle, capacity, make and model" (§9.2).
- "Production volumes and batch sizes at the SU and RU should be compared"; also "minimum and maximum capacity", "material of construction of contact surfaces", "critical operating parameters", components such as filters and sensors, "range of intended use" (§9.5). Utilities "should have sufficient capacity" (§8.1); layout and flows (§9.3); impact on existing products (§9.6). Result: "adaptation of existing equipment or the acquisition of new equipment" (§9.4).
- Practice: gap assessment is "normally done by both the receiving-site and sending-site technical teams" and feeds the transfer plan — [Recipharm author, BioPharm International, 1 Nov 2022 · F](https://www.biopharminternational.com/view/addressing-the-key-pitfalls-hindering-technology-transfer-success). One CDMO checks processing time and yield "through the mass-balance approach" — [Samsung Biologics, 22 May 2024 · F](https://samsungbiologics.com/media/bio-story/accelerating-success-in-biologics-manufacturing-tech-transfer). Eli Lilly authors recommend a shared informal facility-fit spreadsheet — [ISPE iSpeak, undated · S](https://ispe.org/pharmaceutical-engineering/ispeak/technology-transfer-manufacturing-processes-best-practices). "technical fit does not always mean execution fit" — [Drug Development & Delivery, undated · S](https://drug-dev.com/technology-transfer-streamlining-biologics-technology-transfer-through-integrated-operational-models/).

**Document set**

| Document | What guidance states | Source |
|---|---|---|
| Transfer plan / protocol | Objective, scope, team, phases, deliverables, timing of "trial production batches and validation batches", "reference to gap analysis and risk assessments", "acceptance criteria for a successful transfer", "a parallel comparison of premises, equipment, instruments, materials, procedures, and methods" (§7.1) | [WHO · F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf) |
| Gap analysis, risk assessment | ISPE "5.4 Example Gap Analyses for Small Molecule and Large Molecule Processes" plus an FMEA appendix; PDA case "8.6 Performing Process Fit Assessment to Facilitate Technology Transfer" | [ISPE · F](https://ispewebassets.org/files/publications/guidance-documents/ISPE-GPG1-TT3_TOC.pdf); [PDA · F](https://store.pda.org/TableOfContents/TR65TOC.pdf) |
| Process description, flow, materials | "description of manufacturing steps (narrative and process maps or flowcharts and master batch records)", equipment, materials, control strategy (§12.16); "history of process development as well as any historical process changes" (§12.14). Bill of materials not named in WHO; ISPE Appendix 1 checklist is paywalled | [WHO · F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf) |
| Analytical method transfer | Before process-validation testing; by "confirmation testing, comparability testing between SU and RU results, co-validation between laboratories, or through paper-based knowledge transfer"; protocol with acceptance criteria and deviation handling (§12.24–12.25) | [WHO · F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf) |
| Comparability, readiness, PPQ | ISPE "7.5 Analytical Comparability/Similarity and Stability Strategy", "7.6 Process Validation/Process Performance Qualification Strategy", "3.4 Operational Readiness"; PDA "Readiness Stage" precedes "Execution Stage" | [ISPE · F](https://ispewebassets.org/files/publications/guidance-documents/ISPE-GPG1-TT3_TOC.pdf) |
| Engineering runs | BioPhorum (BPOG) paper on "Engineering, Shake-Down, and Wet Test Runs", 2015 | [PDA Journal · S](https://journal.pda.org/node/3978) |
| Transfer report | "the critical parameters as obtained in the SU and RU"; "Changes, deviations, investigations and the relevant appropriate actions taken should be recorded" (§7.3); ISPE Appendix 6 gives an example | [WHO · F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf) |

### Inferences
- WHO's "parallel comparison" plus §9.2 (steps, parameters, equipment) amounts to a specification for a structured SU-vs-RU table.
- Gap analysis recurs at feasibility, planning and execution, so it behaves as a living record.
- In sponsor-to-CDMO transfers, facility-fit work sits with the receiving site's technical team, although WHO also makes the SU assess RU readiness.

### Gaps
- PDA TR 65 and ISPE body text are paywalled (PDA lists $180 member / $325 non-member — [S](https://www.pda.org/bookstore/product-detail/6680-tr-65-revised-technology-transfer)); their gap and facility-fit templates are unverified.
- BioPhorum: no free text on gap or facility-fit contents. Queries: "BioPhorum technology transfer facility fit digital tech transfer publication"; "BioPhorum technology transfer best practice guide drug substance roadmap". Its 2015 overview ([S](https://journal.pda.org/node/3983)) returned 403.
- ISPE iSpeak article body, USP <1224> and ICH Q5E were not opened.

## 2. Which commercial tools produce a structured sending-vs-receiving comparison rather than a document, and how does the user review and act on gaps?

### Takeaway
Only QbDVision (documented) and Emerson DeltaV PSM (claimed) show an element-level sending-vs-receiving comparison with flagged differences. BioSolve and BioPAT Process Insights calculate equipment or scale fit. The rest manage batch data, parameters, schedules or models. No tool reviewed documents a sponsor-CDMO open-items tracker. Independent evidence is almost absent.

### Cited Findings

| Tool | What it does for transfer | How the user interacts | Evidence |
|---|---|---|---|
| **QbDVision** | "side-by-side analysis of process elements across sites to identify gaps and risks"; "Compare process requirements against equipment capabilities and validated ranges."; "Generate protocols, reports, and batch records using your live data."; no open-item tracking described — [platform page, undated · F](https://www.qbdvision.com/platform/tech-transfer) | Copy a process to create the Receiving Site; copied elements link automatically, later ones are "manually linked"; a Change column shows differences for chosen "Change Criteria", set per project and record type by admins; child pages cover bulk updates, sorting, risk assessment — [user docs, 21 Aug 2025 · F](https://cherrycircle.atlassian.net/wiki/spaces/QK/pages/1945763926/Tech+Transfer) | VC + VD; headline "from two years to two months" unverified; customer stories are vendor-published |
| **Emerson DeltaV PKM** (PSM, Recipe Transfer Management; ex-Fluxa — [S](https://emerson.com/en-us/news/corporate/emerson-acquires-fluxa)) | "structured repository, flexible specification model, and collaboration environment for drug recipe development"; facility-fit scenarios with exception reporting; side-by-side differences across recipe versions and sites; transfer in "almost one click"; up to 12 months saved — [PSM page, undated · F](https://www.emerson.com/en/automation-systems/deltav/deltav-operations-management-software/process-specification-management) | ISA-88 drag-and-drop authoring; calculation engine instead of Excel; check-in/out, comments, approvals | VC; Roche co-built its Modality Library — [18 Nov 2025 · F](https://www.emerson.com/en-us/news/2025/emerson-modality-library-innovation-life-sciences-collab-roche) |
| **IDBS Polar BioProcess / Polar Control** | BioProcess: unit-operation execution data; reports "Exception Report", "Campaign Report", "Bioreactor Comparison" (runs, not sites) — [undated · F](https://www.bioprocessonline.com/doc/polar-biopharma-lifecycle-management-0001). Control: versioned parameters and process definitions for late-stage teams and CDMOs — [7 Mar 2025 · F](https://www.selectscience.net/article/idbs-unveils-idbs-polar-control-revolutionizing-process-management-in-biopharmaceutical-development) | Capture at execution; interactive reports | VC |
| **Skyland PIMS** (IDBS since [16 Nov 2021 · F](https://prnewswire.com/news-releases/idbs-acquires-skyland-analytics-to-extend-lifecycle-management-capabilities-of-polar-301425446.html)) | Batch-data backbone with specification limits; "Sponsors can receive secure, real-time data transmission of batch and quality data." — [undated · F](https://www.pharmaceuticalonline.com/doc/biopharma-manufacturing-process-data-made-simple-with-skyland-pims-0001) | Configured by business users | VC; customers unnamed |
| **Körber PAS-X Savvy / MES** | Savvy spans "bioprocess R&D, scale-up and tech transfer": contextualised data, plots, report templates — [undated · F](https://www.pharmaceuticalonline.com/doc/werum-pas-x-savvy-software-production-lifecycle-bioprocess-r-d-scale-up-tech-transfer-validation-and-mfg-0001). MES page is silent on moving recipes between sites — [F](https://www.koerber.com/en/solutions/software-and-ai/life-sciences-mes) | Plots, dashboards, Word export | VC; recipe transfer: no public evidence found |
| **Mareana** | Batch-record digitisation, review by exception, genealogy, CPV — [homepage · F](https://www.mareana.com/). Transfer only as "streamlining information sharing and technology transfer across sites" — [CDMO page · F](https://mareana.com/cdmos/) | Low-confidence fields go to a person | VC; no transfer module found |
| **BioSolve Process** | Bills of materials, fit with receiving-site equipment, shared unit operations; "evaluate the facility fit" — [25 Sep 2026 · F](https://biopharmservices.com/biosolve-software/biosolve-process/use-cases-for-biosolve-process/) | Scenario models | VC |
| **INOSIM; SchedulePro** | Plant simulation for equipment sizing, utilities, "production scheduling and debottlenecking" — [F](https://www.inosim.com/industries/pharmaceutical-industry/). "a finite capacity scheduling (FCS) tool for batch and semi-continuous manufacturing processes" — [F](https://www.intelligen.com/products/schedulepro-overview/) | Models, Gantt charts, recipes | VC; neither page names facility fit or transfer |
| **Sartorius BioPAT Process Insights** | Scale conversion "between Sartorius bioreactors"; "reduces the need for complex spreadsheets" — [4 Nov 2021 · F](https://www.sartorius.com/en/knowledge/science-snippets/simplifying-the-scaling-process-between-bioreactors-1040122) | Set scaling criteria and limits | VC; vendor-linked paper, "from 250 mL to 2000 L" — [2021 · F](https://bioprocessingjournal.com/a-novel-risk-based-approach-for-predicting-the-optimum-set-of-process-and-cell-culture-parameters-for-scaling-upstream-bioprocessing/) |
| **DataHow** | Hybrid models that "transfer knowledge and insight across molecules and scales" — [sponsored interview, 28 Apr 2026 · F](https://chenected.aiche.org/2026/04/data-driven-bioprocessing-conversation-datahows-alessandro-butte) | Not described | VC |
| **ValGenesis Process Lifecycle Suite** | "Trim 6–12 months from your tech transfers"; no site comparison described — [undated · F](https://www.valgenesis.com/solution/streamline-tech-transfers) | Not described | VC |
| **iFactory AI** | LLM reads sending-site SOPs and batch records and "Produces a versioned gap report in days, not months." — [5 May 2026 · F](https://ifactoryapp.com/sap-integration/on-prem-ai/tech-transfer-digital-twin) | It "routes to the right SME"; humans sign off | VC; no named customers |

- Bayer before QbDVision: "There was a gap analysis XLS file for every unit operation and batch record type," — [vendor-published, 30 Sep 2025 · F](https://www.qbdvision.com/resources/case-study-bayer).

### Inferences
- The documented review pattern is one row per linked element, a change flag and a risk entry; what counts as a change is configurable per record type.
- Equipment fit is split: process-definition tools hold requirements, modelling tools hold equipment capability and scale calculations.

### Gaps
- QbDVision risk-assessment page not opened; Emerson data sheets returned empty, so its facility-fit method is unverified.
- Queries: "Körber PAS-X recipe transfer MBR tech transfer PAS-X Savvy"; "facility fit assessment tech transfer INOSIM OR SchedulePro OR SuperPro biopharma case study"; "Mareana tech transfer software process comparison knowledge graph".
- Dassault BIOVIA and Tulip products not examined.

## 3. How do sponsors and CDMOs share and track open items, deviations, change requests and decisions during a transfer?

### Takeaway
Reported practice is project managers, tiered meetings and joint steering committees, with email, shared drives, SharePoint or Box and generic project tools underneath. Quality-system portals are replacing email for deviations and change control. No source describes a transfer-specific open-items system.

### Cited Findings
- Both sides "communicate through email, calls, and fax". AstraZeneca: "Quality processes were previously mostly manual, with email used to track progress and communicate" — [Veeva white paper, 2026, vendor-authored, named customers · F](https://www.veeva.com/wp-content/uploads/2026/05/Veeva-Accelerate-Lead-Times-Through-Seamless-External-Collaboration-in-Quality.pdf).
- Contractors typically "only provide batch records in PDF or Excel files for weekly or monthly submissions"; "automation of data exchange is a lower priority for less-frequent activities like Tech Transfer." — [IDBS authors, Drug Development & Delivery, Mar 2024 · F](https://drug-dev.com/?p=140955).
- "Products such as SharePoint or Box offers secure, version-controlled document sharing" — [Outsourced Pharma, undated editorial · F](https://www.outsourcedpharma.com/topic/cdmo-onboarding-tech-transfer).
- "a joint steering committee brings together members of our site leadership team and the sponsor's team"; "our project managers serve as the primary point of contact for customers" — [Lonza Capsugel, PharmTech, 9 Jul 2026 · F](https://www.pharmtech.com/view/structuring-tech-transfer-for-optimized-collaboration).
- "weekly operational meetings and monthly management reviews are often effective"; on deviations, sponsors "get upset when they learn about it late." — [CDMO chief executive, PharmTech, 4 Aug 2026 · F](https://www.pharmtech.com/view/how-to-maintain-a-productive-sponsor-cmo-relationship).
- Without agreed decision rights, "the sponsor finds out what was decided whenever the CDMO gets around to saying so."; the proposed matrix sets approver, notification window and change-control owner, e.g. "CDMO notifies sponsor within 24 to 48 hours" for batch-record deviations — [Outsourced Pharma, 29 Jul 2026 · F](https://www.outsourcedpharma.com/doc/the-decision-rights-matrix-making-sponsor-cdmo-governance-enforceable-0001).
- Single points of contact on each side; sponsors travel to the site "to witness activities and be on hand" — [Outsourced Pharma, 7 Jan 2025 · F](https://www.outsourcedpharma.com/doc/focus-areas-to-establish-a-win-win-relationship-with-your-cdmo-0001). WHO: "targeted on-site or virtual visits between the SU and RU at critical phases" (§5.17) — [F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf).
- One CDMO "had been using Smartsheet, but not to its full potential"; consultants added intake forms and "An executive dashboard" — [IPM case study, undated (2025 URL), consultant-authored · F](https://www.ipmcinc.com/wp-content/uploads/2025/10/Consistent-Tech-Transfer-Processes-Enable-CDMO-Growth_IPM-Case-Study.pdf).
- A client portal lets clients "monitor progress, access key documents, and exchange data seamlessly" — [Samsung Biologics, 23 Oct 2025, CDMO claim · F](https://samsungbiologics.com/media/bio-story/ask-our-experts-technology-transfer-with-speed-and-reliability).
- "there was no master document to track all the information and it was sent out piecemeal to different points of contact." — [Kymanox founder, Pharma Manufacturing, 6 Jan 2010 · F](https://www.pharmamanufacturing.com/production/automation-control/article/11360855/pharmaceutical-tech-transfer-tech-transfer-do-it-right-the-first-time-pharmaceutical-manufacturing).
- Guidance: "The communication mechanisms regarding MAA changes and GMP issues should be defined in relevant documentation, including contracts with CMOs." — [ICH Q12, 2019 · F](https://database.ich.org/sites/default/files/Q12_Guideline_Step4_2019_1119.pdf).

### Inferences
- Deviations and change requests have a system of record (each party's quality system). Transfer questions, open items and decisions do not; they live in minutes, trackers and email.

### Gaps
- "Person-in-plant": no public evidence under that term. Query: "sponsor CDMO tech transfer action item tracker joint project team person in plant communication plan governance steering committee".
- No source showed a real shared tracker's columns or usage.

## 4. What evidence is there that spreadsheets, Word and email still dominate, and what pain does that cause?

### Takeaway
The evidence is consistent but qualitative: an industry consortium, CDMO staff, one sponsor case and many vendors describe document, Excel and email-based transfers. No public percentage was found.

### Cited Findings
- Transfer "has traditionally relied on static documents, spreadsheets, and institutional knowledge" — [CHEManager on the BioPhorum playbook, 21 Oct 2026 · F](https://chemanager-online.com/en/news/biophorum-039-s-digital-technology-transfer-playbook).
- "Initially our whole tech transfer workflow was Excel-based."; "XLS files were unstructured, with no distinction between parameters, materials, process components,"; "Because contributing teams worked offline from each other, duplicated outputs were common."; "Processing that information took 3-6 people meeting 3 times a week for up to 6 weeks at a time." — [Bayer lab lead, vendor-published, 30 Sep 2025 · F](https://www.qbdvision.com/resources/case-study-bayer).
- "We often get data transfer from clients via SharePoint or Excel spreadsheets, or even paper" — [Fujifilm Diosynth, Sartorius panel, 12 Aug 2021 · F](https://www.sartorius.com/en/knowledge/science-snippets/leveraging-digitalization-insights-from-biopharma-cdmos-930088).
- "Traditional ways of storing project data, via Microsoft Excel and Word," are being replaced — [Recipharm author, 1 Nov 2022 · F](https://www.biopharminternational.com/view/addressing-the-key-pitfalls-hindering-technology-transfer-success).
- "most companies still rely on document-based, manual, people-dependent processes" — [Tech-Clarity with Dassault BIOVIA, 10 May 2022 · F](https://tech-clarity.com/tech-transfer-webcast/11373); the survey covered "over 200 companies", percentages gated — [15 Jul 2019 · F](https://tech-clarity.com/techtransfer/8032).
- "Traditionally, scaling has most often been performed using arithmetic in a spreadsheet" — [BioProcess J, 2021 · F](https://bioprocessingjournal.com/a-novel-risk-based-approach-for-predicting-the-optimum-set-of-process-and-cell-culture-parameters-for-scaling-upstream-bioprocessing/).
- Pain: "Manual packages increase duplicate work, version drift, and delays" — [ValGenesis, 2 Jul 2026, VC · F](https://www.valgenesis.com/blog/pharma-tech-transfer-faqs-reducing-risk-cost-and-scale-up-delays). Manual exchange brings "cybersecurity risks, human errors, and potential delays." — [IDBS authors, Mar 2024 · F](https://drug-dev.com/?p=140955).
- Equipment found late: "commercial transfers between sites often require equipment modifications and process adaptations, which add complexity." — [McKinsey, 23 Jul 2020 · F](https://karriere.mckinsey.de/industries/life-sciences/our-insights/why-tech-transfer-may-be-critical-to-beating-covid-19).

### Inferences
- The best-documented pain is reconciliation effort (meetings, duplicated outputs), more than transcription error.

### Gaps
- No direct evidence on re-keying or missed parameters. Queries: "Tech-Clarity tech transfer survey biopharma digital document-based percent report"; "tech transfer spreadsheets email Word documents SharePoint CDMO sponsor manual re-keying version control problem biopharma".

## 5. Where do practitioners say data gets left out or lost during transfers?

### Takeaway
Named losses are process rationale, operator and equipment know-how, development history, and incomplete or outdated packages. No source addressed scale-down model data.

### Cited Findings
- Operator techniques and equipment nuances are "often absent from standard operating procedures"; also "the 'why' behind the process that documents alone rarely capture." — [Kindeva, PharmTech panel, 27 Jul 2026 · F](https://www.pharmtech.com/view/technology-transfer-between-contractors-a-panel-discussion-part-1).
- "Not all process data captured during R&D appears in transfer documentation." — [Bioprocess Online guest column, 2 Jun 2026 · F](https://www.bioprocessonline.com/doc/avoiding-common-pitfalls-in-cdmo-sponsor-relationships-through-integrated-execution-models-0001).
- The CDMO "often inherits a patchwork of documentation and untested process assumptions." — [Outsourced Pharma chief editor, 4 Aug 2025 · F](https://www.bioprocessonline.com/doc/tech-transfer-a-high-stakes-game-of-trust-0001).
- "It's not unusual for us to have a process transferred that has only been run once" — [Fujifilm Diosynth, 12 Aug 2021 · F](https://www.sartorius.com/en/knowledge/science-snippets/leveraging-digitalization-insights-from-biopharma-cdmos-930088).
- "key details are often incomplete or unavailable at the outset" — [Lonza Capsugel, 9 Jul 2026 · F](https://www.pharmtech.com/view/structuring-tech-transfer-for-optimized-collaboration).
- "Commonly overlooked documents include cleaning recovery protocols, raw material qualifications, risk assessments." — [Kindeva, 8 Nov 2024 · F](https://www.kindevadd.com/resources/addressing-top-tech-transfer-challenges/).
- PDA case-study title: "Failed Process Qualification Due to Incomplete Process Readiness & Knowledge Transfer" — [PDA contents · F](https://store.pda.org/TableOfContents/TR65TOC.pdf). WHO lists "History of changes and change management" and "Pilot batch information" as transfer documents (Appendix 1) — [F](https://gmp-compliance.org/files/guidemgr/WHO%20TRS1044-annex4-technology-transfer-in-pharmaceutical-manufacturing.pdf).

### Inferences
- What is lost is mostly context attached to a parameter or step (why, history, deviations), not the values themselves.

### Gaps
- Scale-down model data and historical deviations: no practitioner statement on how they are lost.

## 6. What durations, costs, failure or delay rates and causes of trouble are reported?

### Takeaway
Durations range from 3 months (CDMO marketing) to more than 30 months (vaccines). No rigorous failure-rate or cost survey was found. Analytical method transfer is the most consistently named cause of delay.

### Cited Findings

| Figure | Source |
|---|---|
| "Tech-transfer times for sterile dosage forms, such as injectable vaccines, range from 18 to more than 30 months"; "Transfer steps typically take 27 to 29 months"; "Transfers to an external party take on average 5.8 months longer"; best practice "eight to 11 months" | [McKinsey, 23 Jul 2020, benchmarks without sample size · F](https://karriere.mckinsey.de/industries/life-sciences/our-insights/why-tech-transfer-may-be-critical-to-beating-covid-19) |
| "as short as three months, half the industry average of six months" | [Samsung Biologics, 22 May 2024, CDMO claim · F](https://samsungbiologics.com/media/bio-story/accelerating-success-in-biologics-manufacturing-tech-transfer) |
| Gene-therapy CDMO onboarding "from 6-12 months to 3 months" | [Viralgen, vendor-published, 1 Apr 2026 · F](https://www.qbdvision.com/resources/case-study-viralgen) |
| "Six‑month targets stretch to 18"; "every month saved can mean $3 million to $30 million in revenue gains" | [ValGenesis, undated, VC · F](https://www.valgenesis.com/solution/streamline-tech-transfers) |
| Assay problems cost one CMO six months; automation finished "two years behind the original schedule"; surprises can "add an entire multiple to the project cost" | [Kymanox, 6 Jan 2010 · F](https://www.pharmamanufacturing.com/production/automation-control/article/11360855/pharmaceutical-tech-transfer-tech-transfer-do-it-right-the-first-time-pharmaceutical-manufacturing) |

- Analytical: "analytical assay transfer problems are the top reason for biotech tech transfer delays" — [Kymanox, 2010 · F](https://www.pharmamanufacturing.com/production/automation-control/article/11360855/pharmaceutical-tech-transfer-tech-transfer-do-it-right-the-first-time-pharmaceutical-manufacturing); "Analytical method transfers are often a significant source of delay and failure" — [PharmTech, 9 Jul 2026 · F](https://www.pharmtech.com/view/structuring-tech-transfer-for-optimized-collaboration).
- Priority and communication: transfers "can receive little priority at donor sites and often are not top of mind at receiving sites."; "communications between functions within a company and especially between companies have historically not been smooth." — [McKinsey · F](https://karriere.mckinsey.de/industries/life-sciences/our-insights/why-tech-transfer-may-be-critical-to-beating-covid-19).
- Materials and equipment: "Materials don't behave as advertised."; "in a new facility with different equipment and configurations" — [Outsourced Pharma, 4 Aug 2025 · F](https://www.bioprocessonline.com/doc/tech-transfer-a-high-stakes-game-of-trust-0001).

### Inferences
- The 3-to-6-month and 18-to-30-month figures measure different things (CDMO biologics onboarding versus end-to-end sterile or vaccine transfer including filing) and are not comparable.

### Gaps
- QbDVision attributes "$38M–$389M personnel costs for a 28-month vaccine transfer" to McKinsey ([F](https://www.qbdvision.com/resources/how-a-digital-cmc-platform-enables-rapid-tech-transfer)); that figure was not in the McKinsey text I read. Unverified.
- A "~50% of transfers have quality problems (CDMO Live 2025)" figure appeared only in a search summary with no traceable page. Not citable. Query: "biologics tech transfer duration months cost million delay rate survey CDMO tech transfer statistics".
- "12 to 18 months" for biologics comes from an anonymous, unsourced blog ([Jun 2026 · F](https://bioprocesstools.com/blog/technology-transfer-biologics/)). Low reliability.

## 7. What digital tech transfer standards and initiatives are emerging?

### Takeaway
BioPhorum published a digital tech transfer playbook in August 2026 (gated). Regulatory structured-data work (ICH M4Q(R2), M16, FDA PQ/CMC) targets submissions and runs to 2030. ISA-88 is the recipe model referenced by both vendors and ICH M16.

### Cited Findings

| Initiative | Status and content | Source |
|---|---|---|
| BioPhorum "Digital Technology Transfer Playbook: Guiding Principles" | Published 4 Aug 2026; "introduces the foundational principles of digital technology transfer (DTT)"; covers structured data objects, digital product definitions, ISA-88, AI, digital twins. Full text gated | [BioPhorum · F](https://www.biophorum.com/download/digital-technology-transfer-playbook-guiding-principles/) |
| BioPhorum technology maturity matrix | Route from manual operations to "fully lights-out facilities", including automated transfers | [BioProcess International, 31 Aug 2026 · F](https://www.bioprocessintl.com/information-technology/ebook-technology-transfer-minding-the-gaps-amid-digital-transformation) |
| ISA-88 recipes | "With a general recipe built in the R&D stage," sites generate their own master recipes (Johnson & Johnson); "Tech transfers can be 40 percent faster, and require 50 percent less effort to validate." (attribution unclear) | [Automation World, 18 Dec 2015 · F](https://automationworld.com/products/software/blog/13314703/cutting-time-from-rd-to-manufacturing) |
| Pistoia Alliance | CMC process ontology based on ISA-88/95 to standardise lab and plant recipes for digital transfers | [S; page returned 404](https://www.pistoiaalliance.org/?p=20266) |
| ICH M4Q(R2) | Step 2a May 2025; consultation closed Mar 2026 with "over 2500 comments"; "Jun, 2027 Step 3 Sign-off and Step 4 Adoption of Final Guideline" | [ICH work plan, 10 Jul 2026 · F](https://database.ich.org/sites/default/files/ICH53_M4QR2_EWG_WorkPlan_2026_0818.pdf) |
| ICH M16 Structured Product Quality Submissions | Endorsed 18 Aug 2026; problem: "High volume of unstructured quality information (e.g., free text in PDF)"; annexes to use "ISO IDMP, HL7 FHIR and IEC 61512-1:2026"; Core Guideline June 2027, Step 4 November 2030 | [ICH concept paper · F](https://database.ich.org/sites/default/files/ICH_M16_Concept_Paper_Final_20260818.pdf) |
| FDA PQ/CMC | Aim: "ultimately support submission of ICH CTD Module 3 information in structured format using HL7 FHIR"; later stages add batch formula, batch analysis, stability, manufacturing, biologics; FDA acceptance not announced. HL7 guide at STU2 ([S](https://hl7.org/fhir/us/pq-cmc-fda/STU2/)) | [FDA, current as of 16 Jan 2025 · F](https://www.fda.gov/industry/pharmaceutical-quality-chemistry-manufacturing-controls-pqcmc/pqcmc-and-hl7-fhir) |
| ICH Q12 | "ECs are legally binding information considered necessary to assure product quality."; the PLCM document is "a central repository for the ECs"; protocols can cover "change in manufacturing site(s) across multiple products" | [ICH Q12, 20 Nov 2019 · F](https://database.ich.org/sites/default/files/Q12_Guideline_Step4_2019_1119.pdf) |

### Inferences
- Structured standards target regulator-facing content first; sponsor-CDMO exchange formats will likely stay proprietary or ad hoc for several years.
- Tagging compared parameters as established conditions versus supportive information would show which gaps carry a filing consequence.

### Gaps
- BatchML (MESA) as the ISA-88 exchange format: seen only in a search summary, no URL captured. Unverified.
- Playbook content, contributors and any BioPhorum data on current practice are gated.
- The session's shared WebSearch budget ran out mid-task; two planned searches (BioPhorum playbook detail, Mareana product pages) were not run. Rockwell, TCS, Pharma's Almanac, PharmaSource and PDA pages returned 403, 429 or 503.
