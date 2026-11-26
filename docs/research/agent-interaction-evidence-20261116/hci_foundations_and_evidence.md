# HCI foundations and evidence for human–agent interaction beyond chat

Researched 2026-11-16. Tags: **FETCHED†** = PDF text read directly (verbatim; ligatures normalised). **FETCHED** = opened with the fetch tool, which relays quotes of at most 125 characters (spot-check before print). **SNIPPET** = search result only. The web-search budget ran out mid-task; see Gaps.

## 1. When should a system act, ask, or stay silent, and how is interruption cost weighed?

### Takeaway
Horvitz (1999) frames act / ask / do nothing as an expected-utility choice with two probability thresholds that move with the cost of a wrong action and the user's attention; Amershi et al. (2019) restate this as timing, dismissal, correction and scoping guidelines. Neither concerns LLM agents.

### Cited Findings
- **Horvitz, E. (1999). "Principles of Mixed-Initiative User Interfaces." Proc. CHI '99, 159–166** (pages per Amershi's reference list). [FETCHED†](https://erichorvitz.com/chi99horvitz.pdf)
  - Twelve "critical factors", verbatim: (1) "Developing significant value-added automation"; (2) "Considering uncertainty about a user's goals"; (3) "Considering the status of a user's attention in the timing of services"; (4) "Inferring ideal action in light of costs, benefits, and uncertainties"; (5) "Employing dialog to resolve key uncertainties"; (6) "Allowing efficient direct invocation and termination"; (7) "Minimizing the cost of poor guesses about action and timing"; (8) "Scoping precision of service to match uncertainty, variation in goals"; (9) "Providing mechanisms for efficient agent−user collaboration to refine results"; (10) "Employing socially appropriate behaviors for agent−user interaction"; (11) "Maintaining working memory of recent interactions"; (12) "Continuing to learn by observing".
  - Act: "Autonomous actions should be taken only when an agent believes that they will have greater expected value than inaction for the user". eu(A|E) = p(G|E)·u(A,G) + [1−p(G|E)]·u(A,¬G); act only above the crossover probability p*.
  - Ask: dialog typically beats a wrong action and loses to a right one, giving two thresholds for "whether to act, to engage the user in a dialog about action, or to do nothing". "Thresholds can be directly assessed by designers or users."
  - Interruption: "The utility of unwanted action can diminish significantly with increases in the depth of a user's focus on another task. Such a reduction in the value of action leads to a higher probability threshold." Factor 5 weighs "the costs of potentially bothering a user needlessly"; factor 8 prefers '"doing less" but doing it correctly under uncertainty'.
  - Limits: one prototype (LookOut, email to calendar); timing data "from several users"; no controlled evaluation.
- **Amershi, S. et al. (2019). "Guidelines for Human-AI Interaction." CHI 2019, doi 10.1145/3290605.3300233.** [FETCHED†](https://www.microsoft.com/en-us/research/uploads/prod/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf)
  - Table 1, verbatim. *Initially:* G1 "Make clear what the system can do"; G2 "Make clear how well the system can do what it can do". *During interaction:* G3 "Time services based on context"; G4 "Show contextually relevant information"; G5 "Match relevant social norms"; G6 "Mitigate social biases". *When wrong:* G7 "Support efficient invocation"; G8 "Support efficient dismissal"; G9 "Support efficient correction"; G10 "Scope services when in doubt"; G11 "Make clear why the system did what it did". *Over time:* G12 "Remember recent interactions"; G13 "Learn from user behavior"; G14 "Update and adapt cautiously"; G15 "Encourage granular feedback"; G16 "Convey the consequences of user actions"; G17 "Provide global controls"; G18 "Notify users about changes".
  - G3: "Time when to act or interrupt based on the user's current task and environment." G10: "Engage in disambiguation or gracefully degrade the AI system's services when uncertain about a user's goals."
  - Validation: "49 design practitioners who tested the guidelines against 20 popular AI-infused products"; G11 "had one of the highest number of violations".
  - Limits: 2019 products (recommenders, voice assistants), not agents; relevance, not outcomes.
- **Microsoft HAX Toolkit** (undated) [FETCHED](https://www.microsoft.com/en-us/haxtoolkit/): the guidelines plus a Design Library, Workbook and Playbook; no outcome data.
- Anthropic (2026, §2): its agent "stops to ask for clarification more than twice as often as humans interrupt it" on the most complex tasks.

### Inferences (mine)
- Set act / ask / silent thresholds per action class, raised by irreversibility and user focus, not one global confirmation policy.
- Under uncertainty, a smaller correct step (draft, scoped view) can beat both a question and a full guess (factor 8, G10).
- Cheap invoke, dismiss and correct paths (factor 6, G7–G9) make acting without asking tolerable.

### Gaps
- No fetched source measures interruption cost for LLM agents; Horvitz's utilities are designer-assessed.

## 2. Autonomy-level frameworks, the human's role at each level, and variation by task or time

### Takeaway
Feng et al. (2025) define five levels by the user's role and treat autonomy as a design decision separate from capability; Shneiderman rejects one-dimensional scales in favour of high automation with high control. Vendor telemetry shows users widening autonomy with experience while moving from approving to monitoring.

### Cited Findings
- **Feng, K. J. K., McDonald, D. W. & Zhang, A. X. (2025). "Levels of Autonomy for AI Agents."** arXiv:2506.12469, v1 14 Jun 2025 [FETCHED](https://arxiv.org/html/2506.12469v2); Knight First Amendment Institute, 28 Jul 2025 [FETCHED](https://knightcolumbia.org/content/levels-of-autonomy-for-ai-agents-1).
  - Autonomy is "the extent to which it is designed to act without user involvement" and "can instead be a deliberate design decision made by agent developers"; "more autonomy does not simply mean a better agent".

| Level, user role | Source wording | Control named |
|---|---|---|
| L1 operator | "the user is in charge at all times" | "Invocation or approval before actions" |
| L2 collaborator | "User and agent collaboratively plan, delegate, and execute tasks." | "Shared representation of progress" |
| L3 consultant | "Agent plans and executes most tasks"; user "consulted to contribute expertise and relevant preferences" | "Rich user feedback elicitation interfaces" |
| L4 approver | "Agent requests user involvement only when it reaches a failure or high-risk state" | "Approval elicitation for consequential actions" |
| L5 observer | "Agent plans and executes all tasks"; user can "monitor and audit agent via activity logs" | "Emergency off switch" |

  - Autonomy certificate: "a digital document that prescribes the maximum level of autonomy at which an agent can operate", "issued by a third-party governing body to agent developers".
  - Limits: conceptual essay, no user data; the fetch found no dial or slider language.
- **Sheridan, T. B. & Verplank, W. L. (1978). "Human and computer control of undersea teleoperators." MIT Man-Machine Systems Lab.** Original not opened; wording from the reproduction in Beer, Fisk & Rogers (2014), J. Human-Robot Interaction 3(2):74–99 [FETCHED](https://pmc.ncbi.nlm.nih.gov/articles/PMC5656240/): "The computer offers no assistance; the human must take all decisions and actions." → "offers a complete set of decision/action alternatives" → "Narrows the selection down to a few" → "Suggests one alternative" → "Executes that suggestion if the human operator approves" → "Allows the human a restricted time to veto before automatic execution" → "Executes automatically, then necessarily informs the human" → "Informs the human only if asked" → "Informs the human only if it, the computer, decides to". Top level, computer "decides everything, acts autonomously, ignoring the human": [SNIPPET](https://www.mitre.org/sites/default/files/pdf/pr-16-3426-lessons-lost-automation-in-aviation-definition-of-automation.pdf). Limits: the reproduction's row numbers are corrupted, so level numbers are unverified.
- **Parasuraman, R., Sheridan, T. B. & Wickens, C. D. (2000). "A model for types and levels of human interaction with automation." IEEE Trans. SMC-A 30(3):286–297.** Abstract only [FETCHED](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:10.1109/3468.844354&resultType=core&format=json). Automation applies to "1) information acquisition; 2) information analysis; 3) decision and action selection; and 4) action implementation", each "across a continuum of levels from low to high"; secondary criteria include "the costs of decision/action consequences".
- **Shneiderman, B. (2020). "Human-Centered Artificial Intelligence: Reliable, Safe & Trustworthy."** arXiv:2002.04087, 23 Feb 2020 [FETCHED†](https://arxiv.org/pdf/2002.04087). "The new goal is to seek high levels of human control AND high levels of automation"; the Sheridan–Verplank list suggests "that increases in automation must come at the cost of lowering human control". Limits: conceptual.
- **Morris, M. R. et al. (ICML 2024). "Levels of AGI for Operationalizing Progress on the Path to AGI."** [FETCHED](https://arxiv.org/html/2311.02462v5). Six levels, "No AI" to "AI as an Agent"; "lower levels of autonomy may be desirable for particular tasks and contexts".
- **Mitchell, M. et al. (2025). "Fully Autonomous AI Agents Should Not be Developed."** arXiv:2502.02649 [FETCHED](https://arxiv.org/html/2502.02649v3). Position paper: "The more control a user cedes to an AI agent, the more risks to people arise."
- **Karpathy, A. (17 Jun 2025). "Software Is Changing (Again)", YC AI Startup School.** Unofficial, error-prone transcript [FETCHED](https://www.donnamagi.com/articles/karpathy-yc-talk). "there should be an autonomy slider in your product"; "you can speed up verification a lot"; "GUIs, for example, are extremely important for this". Limits: opinion.
- **Yocco, V. (11 Feb 2026). "Designing For Agentic AI: Practical UX Patterns For Control, Consent, And Accountability." Smashing Magazine.** [FETCHED](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/). "Autonomy Dial": Observe & Suggest; Plan & Propose; Act with Confirmation; Act Autonomously, "ideally on a per-task-type basis". Limits: practitioner pattern, no data.
- **Anthropic (18 Feb 2026). "Measuring AI agent autonomy in practice."** [FETCHED](https://www.anthropic.com/research/measuring-agent-autonomy). 998,481 API tool calls plus Claude Code session samples of 500k.
  - "Among new users, roughly 20% of sessions use full auto-approve, which increases to over 40% as users gain experience" (under 50 versus about 750 sessions).
  - Interruptions rise from about 5% to about 9% of turns; users "shift from approving individual actions to monitoring what the agent does".
  - "only 0.8% of actions appear to be irreversible".
  - "effective oversight doesn't require approving every action but being in a position to intervene when it matters".
  - Limits: vendor's own traffic; model-generated labels; observational.
- Anthropic (Aug 2026, §5): "As of June 2026, 49.5% of active CLI users have manually created a Bash allow-rule".

### Inferences (mine)
- Treat autonomy as a product setting per task type, not a model property (Feng, Morris, Yocco).
- L3 "consult for preferences" and L4 "approve consequential actions" need different surfaces; one approval dialog conflates them.
- Raising automation should add controls (visibility, undo, interruption); Sheridan's middle rungs (approve, veto window, inform after) give a vocabulary for per-action notification policy.

### Gaps
- Could not verify the Sheridan–Verplank original or Parasuraman's Table I (four hosts returned 403). Query: `Parasuraman Sheridan Wickens 2000 "A model for types and levels of human interaction with automation" PDF`.
- Could not verify Karpathy's wording against an official transcript. Query: `Karpathy "Software Is Changing (Again)" transcript "autonomy slider"`.
- No independent longitudinal data on how users grant autonomy.

## 3. Strongest arguments against chat as the primary interface, and the alternatives proposed

### Takeaway
The critiques converge on four costs of chat: no visible affordances, the burden of putting intent into prose, slow input, and loss of direct control. Nearly all propose hybrids. All are essays or debate, not comparative studies.

### Cited Findings
- **Wattenberger, A. "Why Chatbots Are Not the Future."** Undated on page (unverified recollection: 2023). [FETCHED](https://wattenberger.com/thoughts/boo-chatbots). "Good tools make it clear how they should be used."; "the burden to learn what works still lies with every single user." Alternatives: guidance "baked into the interface", sliders, letting "the user choose when to switch between implementation and evaluation".
- **Appleton, M. "Language Model Sketchbook, or Why I Hate Chatbots."** "Planted over 3 years ago". [FETCHED](https://maggieappleton.com/lm-sketchbook). "We are irreversibly anchored to this text-heavy, turn-based interface paradigm." Alternatives: background "Daemons" that "suggest ideas to you every now and then"; Epi, which "uses the familiar right-click context menu". Limits: concept sketches.
- **Nielsen, J. (18 Jun 2023). "AI: First New UI Paradigm in 60 Years." NN/g.** [FETCHED](https://www.nngroup.com/articles/ai-paradigm/). Intent-based outcome specification: "the user tells the computer what outcome they want", which "completely reverses the locus of control". He predicts a "hybrid user interface".
- **Nielsen, J. (24 May 2023, updated 1 Apr 2025). "The Articulation Barrier: Prompt-Driven AI UX Hurts Usability." UX Tigers.** [FETCHED](https://www.uxtigers.com/post/ai-articulation-barrier). Users "must be highly articulate to write the required prose text for the prompts". He estimates under 20% (best guess 10%) of rich-country populations can prompt at an advanced level. Limits: extrapolated from OECD PIAAC reading scores; no prompting study.
- **Shneiderman, B. & Maes, P. (1997). "Direct manipulation vs. interface agents." interactions 4(6), Nov–Dec 1997.** [FETCHED†](https://www.cs.umd.edu/users/ben/papers/Shn-Maes-v4n6-1997.pdf)
  - Shneiderman: "environments where users comprehend the display, where they feel in control, where the system is predictable, and where they are willing to take responsibility for their actions". He concedes "two levels": a predictable interface with adaptive algorithms "below the table".
  - Maes: "whenever workload or information load gets too high, there is a point where a person has to delegate"; "We cannot just add more and more sliders and buttons." Agents are "a complementary technique to well-designed interfaces—visualization, and direct manipulation—not a replacement"; "Users still need to be able to bypass the agent"; "users must never feel out of control".
- **Litt, G.** (Mar 2023) "Malleable software in the age of LLMs" [FETCHED](https://www.geoffreylitt.com/2023/03/25/llm-end-user-programming): "chat is an essentially limited interaction mode, regardless of the quality of the bot."; alternative: models build tools that users operate directly. (27 Jul 2025) "Enough AI copilots! We need AI HUDs" [FETCHED](https://www.geoffreylitt.com/2025/07/27/enough-ai-copilots-we-need-ai-huds): "design the cockpit so that the human pilot is naturally aware of their surroundings"; "routine predictable work might make sense to delegate".
- **Lehr, J. (27 Mar 2025). "The case against conversational interfaces."** [FETCHED](https://julian.digital/2025/03/27/the-case-against-conversational-interfaces/). Speech about 150 words per minute, typing about 60 (rounded averages); "Natural language might be natural, but it's a bottleneck." Proposal: "an always-on command meta-layer that spans across all tools".

### Inferences (mine)
- The defensible position is hybrid: language for open-ended intent, visible controls for known repeated operations, direct manipulation for refinement.
- Results should land in a structured, editable artefact, not a transcript.
- Delegation must never be the only path (Maes's bypass; Litt's routine-versus-extraordinary split).

### Gaps
- No source here reports comparative user data on chat versus alternatives.

## 4. Empirical evidence: (a) how well non-experts specify intent, (b) how reliably people catch errors

### Takeaway
(a) Direct evidence is thin and qualitative: ten non-experts iterated prompts ad hoc and over-generalised from single trials. (b) Evidence is larger and consistent: people follow wrong advice, generic explanations raise acceptance without raising accuracy, and human–AI teams on decision tasks average worse than the better of the two alone.

### Cited Findings
**(a) Specifying intent**
- **Zamfirescu-Pereira, J. D., Wong, R., Hartmann, B. & Yang, Q. (2023). "Why Johnny Can't Prompt." CHI '23.** [FETCHED†](https://people.eecs.berkeley.edu/~bjoern/papers/zamfirescu-johnny-chi2023.pdf). N = 10. Participants "explored prompt designs opportunistically, not systematically"; struggles "primarily stemmed from (a) over-generalization from single observations of success and failure of prompt changes; and (b) models of system behavior rooted in human-human interactions". Limits: GPT-3 era; task was authoring a chatbot prompt.
- **Subramonyam, H. et al. (2024). "Bridging the Gulf of Envisioning." CHI '24.** [FETCHED](https://arxiv.org/html/2309.14459v2). Gaps: capability, instruction ("challenges in clearly and effectively expressing their intentions") and intentionality ("failure to create clear intentions"). Patterns include "Provide Multiple Outputs" and "Allow manual control of output". Limits: theory; no user study.
- **Tankelevitch, L. et al. (2024). "The Metacognitive Demands and Opportunities of Generative AI." CHI '24.** [FETCHED†](https://arxiv.org/pdf/2312.10893). Prompting demands "self-awareness of task goals, and decomposition of tasks into sub-tasks"; demands "parallel those of a manager delegating tasks to a team". Limits: conceptual.

**(b) Catching errors**
- **Parasuraman, R. & Manzey, D. H. (2010). "Complacency and bias in human use of automation." Human Factors 52(3):381–410.** Abstract [FETCHED](https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:21077562%20AND%20SRC:MED&resultType=core&format=json). "Automation bias occurs in both naive and expert participants, cannot be prevented by training or instructions". Limits: pre-LLM automation.
- **Goddard, K., Roudsari, A. & Wyatt, J. C. (2012). "Automation bias: a systematic review." JAMIA 19(1):121–127.** [FETCHED](https://pmc.ncbi.nlm.nih.gov/articles/PMC3240751/). 74 studies; "erroneous advice was more likely to be followed in the CDSS groups", risk ratio 1.26 (95% CI 1.11–1.44); correct answers switched to incorrect in 6–11% of cases. Limits: clinical decision support.
- **Vaccaro, M., Almaatouq, A. & Malone, T. (2024). "When combinations of humans and AI are useful." Nature Human Behaviour 8:2293–2303.** [FETCHED](https://pmc.ncbi.nlm.nih.gov/articles/PMC11659167/). 106 studies. Human–AI versus the better of either alone: g = −0.23 (95% CI −0.39 to −0.07); versus humans alone: g = 0.64. Decision tasks g = −0.27; creation tasks g = 0.19 (not significant). Explanations and confidence were not significant moderators. Limits: 2020 to mid-2023 laboratory tasks.

| Intervention | Source | Result |
|---|---|---|
| Generic explanations | Bansal et al., CHI 2021 [FETCHED†](https://arxiv.org/pdf/2006.14779) | "explanations increased the chance that humans will accept the AI's recommendation, regardless of its correctness" |
| Explanations that make checking cheap | Vasconcelos et al., CSCW 2023, N = 731 [FETCHED†](https://arxiv.org/pdf/2212.06823); Fok & Weld, 2024 [FETCHED](https://arxiv.org/abs/2305.07722) | Help only when checking costs less; "Most tasks fundamentally do not allow easy verification" |
| Cognitive forcing | Buçinca, Malaya & Gajos, CSCW 2021, N = 199 [FETCHED†](https://arxiv.org/pdf/2102.09692) | "significantly reduced overreliance", but those designs got the "least favorable subjective ratings" |
| Confidence score | Zhang, Liao & Bellamy, 2020 [FETCHED](https://arxiv.org/abs/2001.02114) | "can help calibrate people's trust"; "trust calibration alone is not sufficient" |
| First-person uncertainty wording | Kim et al., FAccT 2024, N = 404 [FETCHED](https://arxiv.org/abs/2405.00623) | Higher accuracy; "reduced (but not fully eliminated) overreliance" |
| Highlighting low-confidence content | Spatharioti et al., 2023 preprint [FETCHED](https://arxiv.org/abs/2307.03744) | "substantially increases the rate at which users spot incorrect information" (no number in abstract) |

- **Passi, S. & Vorvoreanu, M. (Jun 2022). "Overreliance on AI: Literature Review." Microsoft MSR-TR-2022-12.** [FETCHED†](https://www.microsoft.com/en-us/research/wp-content/uploads/2022/06/Aether-Overreliance-on-AI-Review-Final-6.21.22.pdf). About 60 papers; "detailed explanations often lead users to develop overreliance on AI". Limits: predates LLM assistants.
- **Lee, H.-P. et al. (2025). "The Impact of Generative AI on Critical Thinking." CHI '25.** [FETCHED†](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/01/lee_2025_ai_critical_thinking_survey.pdf). 319 knowledge workers: "higher confidence in GenAI is associated with less critical thinking". Limits: self-report, correlational.
- **Dell'Acqua, F. et al. (2023). "Navigating the Jagged Technological Frontier." HBS Working Paper 24-013.** Figures from co-author Mollick's essay, 16 Sep 2023 [FETCHED](https://www.oneusefulthing.org/p/centaurs-and-cyborgs-on-the-jagged). 758 consultants: "40% higher quality" inside the frontier; outside it, correct "84% of the time without AI help" against "60-70%" with AI. Limits: GPT-4 chat, one firm.
- **Becker, J., Rush, N., Barnes, E. & Rein, D. (METR, Jul 2025). "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity."** [FETCHED](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/); [FETCHED](https://arxiv.org/html/2507.09089v2). 16 developers, 246 tasks; completion time rose 19% while developers estimated a 20% reduction; under 44% of generations accepted. Update, 24 Feb 2026 [FETCHED](https://metr.org/blog/2026-02-24-uplift-update/): later tools gave −18% (CI −38% to +9%) and −4% (CI −15% to +9%); METR calls this "very weak evidence" and marks the 2025 result out of date.
- **Mozannar, H., Bansal, G., Fourney, A. & Horvitz, E. (2024). "Reading Between the Lines." CHI 2024.** [FETCHED](https://arxiv.org/html/2210.14306v5). 21 programmers; "(34.3%) on just double-checking and editing Copilot suggestions". Limits: 2022 autocomplete.
- **Bainbridge, L. (1983). "Ironies of Automation." Automatica 19(6):775–779.** [FETCHED†](https://ckrybus.com/static/papers/Bainbridge_1983_Automatica.pdf). "it is impossible for even a highly motivated human being to maintain effective visual attention towards a source of information on which very little happens, for more than about half an hour"; "The human monitor has been given an impossible task." Limits: process control.
- **Simkute, A. et al. (Feb 2024). "Ironies of Generative AI."** arXiv:2402.11364 [FETCHED](https://arxiv.org/abs/2402.11364). Productivity loss from "a shift in users' roles from production to evaluation" and "interruptions". Limits: conceptual.

### Inferences (mine)
- Budget for review: make checking cheaper than redoing (diffs, source-linked claims, re-runnable steps); otherwise expect acceptance without checking.
- Explanations or a confidence number alone do not fix overreliance; combine targeted uncertainty cues with a forced look only where stakes justify friction.
- Self-reported benefit is unreliable (METR); measure task outcomes.
- Support intent before generation: examples, multiple candidates, controls for parameters users cannot name.

### Gaps
- Provenance or citation display: no isolating study located before the search budget ran out.
- Review evidence mostly concerns single recommendations, not multi-step agent runs.
- Could not verify the Dell'Acqua paper directly (SSRN and HBS returned 403).
- No large quantitative study of non-expert prompt quality located.

## 5. Evidence that approval prompts become rubber-stamping, and designs that reduce it

### Takeaway
Vendor data shows near-universal approval of agent permission prompts, and a test in which 13.6% of people stopped a planted dangerous command, with vigilance falling as prompts accumulated. Clinical-alert and browser-warning studies point to fewer, more specific, better-designed interruptions.

### Cited Findings
- **Anthropic (25 Mar 2026). "How we built Claude Code auto mode."** [FETCHED](https://www.anthropic.com/engineering/claude-code-auto-mode). "Manual prompts sit in the middle, and in practice users accept 93% of them anyway."; "approval fatigue, where people stop paying close attention to what they're approving". Its classifier: 0.4% false positives (n = 10,000), 17% false negatives on real overeager actions (n = 52).
- **Anthropic (7 Aug 2026, updated 22 Oct 2026). "Auto mode is now the default in Claude Code."** [FETCHED](https://claude.com/blog/auto-mode-default-in-claude-code); sceptical coverage, The Register, 10 Aug 2026 [FETCHED](https://www.theregister.com/a/5285326).
  - "users approve 97% of permission prompts in Claude Code".
  - "when Claude presents a plan for approval, users reject 39% of them." "But for individual permissions requests, the rejection rate is only 3%."
  - 1,053 paid testers: "The testers caught the dangerous command just 13.6% of the time (143 of 1,053)," "while auto mode blocked 89% of the same commands (937 of 1,053)."
  - "they blocked about 17% of dangerous commands early in a session," "dropping to about 5% after 50 or more prior prompts".
  - Limits: vendor evidence for its own product change, not peer reviewed; testers "knew they were being evaluated" in a purpose-built environment.
- **van der Sijs, H., Aarts, J., Vulto, A. & Berg, M. (2006). "Overriding of drug safety alerts in computerized physician order entry." JAMIA 13(2):138–147.** [FETCHED](https://pmc.ncbi.nlm.nih.gov/articles/PMC1447540/). "Drug safety alerts are overridden by clinicians in 49% to 96% of cases." Remedies: "irrelevant and nonurgent alerts should not be shown"; "Alerts should be directed to the right person".
- **Ancker, J. S. et al. (2017). "Effects of workload, work complexity, and repeated alerts on alert fatigue." BMC Med Inform Decis Mak 17:36.** [FETCHED](https://pmc.ncbi.nlm.nih.gov/articles/PMC5387195/). 112 clinicians, 1,266,325 advisories. Per extra advisory in an encounter, "the likelihood a clinician would accept any BPA dropped by 30%". "Reducing within-patient repeats may be a promising target". Limits: observational.
- **Akhawe, D. & Felt, A. P. (2013). "Alice in Warningland." USENIX Security '13, 257–272.** [FETCHED](https://www.usenix.org/conference/usenixsecurity13/technical-sessions/presentation/akhawe). "over 25 million warning impressions"; click-through of "70.2% of Google Chrome's SSL warnings" against "a third" of Firefox's; "the user experience of a warning can have a significant impact on user behavior."
- **Bravo-Lillo, C. et al. (2013). "Your Attention Please." SOUPS 2013.** [FETCHED†](https://cups.cs.cmu.edu/soups/2013/proceedings/a6_Bravo-Lillo.pdf). After habituation, "Participants exposed to inhibitive attractors were two to three times more likely to make an informed decision".
- Bainbridge and Parasuraman & Manzey (§4): monitoring for rare events fails and training does not prevent it.

### Inferences (mine)
- An approval rate near 100% means the prompt informs nobody; track approval rate per prompt type and retire or automate those always approved.
- Review at plan level, where people still disagree (39%), and reserve per-action prompts for irreversible or out-of-scope actions.
- Cut repeats, tier by severity, route to the right person, and vary the design of rare, serious prompts.
- Human approval is a weak safety control alone; pair it with undo, scoped permissions and automated screening.

### Gaps
- No independent replication of the vendor's tester study; no approval-rate data from other agent products located. The non-vendor evidence concerns clinical alerts and browser warnings, not agents.
- Whether plan-level review catches more real errors, not just more rejections, is not established.
