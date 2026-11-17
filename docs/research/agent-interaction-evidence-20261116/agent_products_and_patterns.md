# Agent products and interaction patterns beyond the chat box (evidence as of 2026-11-16)

Conventions: sources are tagged at first mention. **F** = FETCHED; **S** = SNIPPET (repeated at every use). **V** = vendor documentation/claim, including press relaying vendor statements; **I** = independently evidenced. "n.d." = undated page as fetched 2026-11-16. Quotes came through a passage-extracting fetch tool, so spot-check wording. openai.com and help.openai.com returned 403; the search budget ran out late. ChatGPT Dots excluded per brief.

## What exactly are Magentic-UI's mechanisms and what did its evaluation measure?

### Takeaway
The paper defines six mechanisms: co-planning, co-tasking, action approval, answer verification, memory and multi-tasking. Its evidence is autonomous parity with Magentic-One, gains with LLM-simulated users holding privileged information, a 12-person qualitative study and internal red-teaming; there is no controlled human or productivity result.

### Cited Findings
Sources: [MUI-paper, arXiv 2507.22358v1, 2025-07-30](https://arxiv.org/html/2507.22358v1) F·V; [MUI-blog, 2025-05-19](https://www.microsoft.com/en-us/research/blog/magentic-ui-an-experimental-human-centered-web-agent/) F·V. The blog names four mechanisms (co-planning, co-tasking, action guards, plan learning); the paper adds answer verification and multi-tasking.

| Mechanism | Paper definition | How it works (paper quotes) |
|---|---|---|
| Co-planning | "co-planning to enable collaboration on a plan of action" | "The plan is displayed in an interactive UI component that users can edit directly."; "To begin plan execution, the user must explicitly press the "Accept" button or type "accept"." |
| Co-tasking | "co-tasking to facilitate seamless take-and-hand-over of control" | "Users may pause the task execution at any point"; "the Orchestrator can delegate steps of the plan to the user"; principle: "interrupt the user as little as possible and only when necessary." |
| Action approval ("action guards") | "action approval to ensure oversight of high-stakes actions" | Developer sets an "irreversibility heuristic ... with three possible values": always (human approves), never (auto-run), maybe ("we pass the action proposal to the ActionGuard judge", an LLM told "When unsure, err on the side of caution and require human approval."). Users can set "always ask for permission before performing any action." |
| Answer verification | "answer verification to help validate the task was completed correctly" | Users inspect steps and screenshots or ask follow-ups. |
| Memory (plan learning, retrieval) | "memory to leverage past experience to improve future performance" | "Learned plans are saved in a "Saved Plans" gallery"; "automatic plan retrieval by the Orchestrator using AutoGen's Task Centric Memory". |
| Multi-tasking | "multi-tasking to parallelize execution while staying in the loop" | "Each session has a session status indicator that displays whether user input is required." |

- **Autonomous benchmarks** (Table 1, o4-mini): GAIA test 42.52 (Magentic-One 38.00; best listed 80.04; human 92.00); AssistantBench 27.6 (Magentic-One 27.7); WebVoyager 82.2 (Operator 87.0); WebGames 45.5 (human 95.7). [MUI-paper](https://arxiv.org/html/2507.22358v1)
- **Simulated users** (GAIA validation, 162 tasks; "The simulated user is an LLM without any tools"). One given GAIA "side information, which includes a human-written plan to solve the task" lifted completion "by 71%, from a 30.3% task-completion rate to a 51.9% task-completion rate." The agent "only asks for help from the simulated user in 10% of tasks", "relies on the simulated user for the final answer in 18% of tasks", and "asks for help on average 1.1 times." A smarter-model user without side information "improves to 42.6%", asked "in only 4.3% of tasks". Leakage was prevented "in all but 6% of tasks". [MUI-blog](https://www.microsoft.com/en-us/research/blog/magentic-ui-an-experimental-human-centered-web-agent/)
- **User study**: "We recruited 12 users to participate in an hour-long study."; "The overall SUS score was 74.58". Approval "to add items to cart was not needed, as this action was perceived as low risk"; "some participants trusted the AI's output even when noting they were uncertain"; "Participants especially expressed the utility of screenshots"; some "found it overwhelming to monitor or review long task histories" and found "the number of requests for feedback excessive". [MUI-paper](https://arxiv.org/html/2507.22358v1)
- **Safety**: 24 internal adversarial scenarios; none succeeded by default; with mitigations disabled, prompt injection succeeded. [MUI-paper](https://arxiv.org/html/2507.22358v1)
- **Stated limits**: evaluation "restricted to simulated evaluations and qualitative insights"; productivity needs "long-term controlled trials"; agents sometimes deviate from the plan; plans cannot branch; long plans are costly to edit. [MUI-paper](https://arxiv.org/html/2507.22358v1)
- **2026 status**: the repo now presents "MagenticLite", "the next generation of Magentic-UI", "redesigned to do more with less". Release 0.2.1 is dated 21 May (year not shown). [README-main, n.d.](https://raw.githubusercontent.com/microsoft/magentic-ui/main/README.md) F·V; [releases](https://github.com/microsoft/magentic-ui/releases) F·V

### Inferences
- The 71% gain measures an LLM stand-in that held a human-written solution plan and supplied 18% of final answers; it is not evidence of real-user uplift.

### Gaps
- Figure 11 values (human baseline) and plan-retrieval accuracy numbers are not in the text read.
- Could not verify whether MagenticLite keeps co-planning, the plan gallery or parallel sessions.

## How do ambient/background agents decide when to interrupt a human, and what does the inbox pattern look like in practice?

### Takeaway
In LangChain's pattern the developer fixes interruption points per node or tool and an inbox collects pending items; other products use trained confirmation behaviour, judge or reviewer models, or timers. LangChain left Slack for an inbox because notifications piled up, then archived the open-source inbox in September 2026.

### Cited Findings
- Definition (Harrison Chase): "Ambient agents listen to an event stream and act on it accordingly, potentially acting on multiple events at a time."; "we do not think that ambient agents are necessarily completely autonomous." [LC-ambient, 2025-01-14](https://www.langchain.com/blog/introducing-ambient-agents) F·V
- "We typically see three common human-in-the-loop patterns for ambient agents: notify, question, and review." Notify: "let the user know some event is important, but not take any actions". Question: "ask the user a question to help unblock the agent". Review: "The human can either approve the action, edit it directly, or give direct feedback to the agent on how to change it." [LC-ambient](https://www.langchain.com/blog/introducing-ambient-agents)
- Why an inbox: "When experimenting with ambient agents we initially started with Slack."; "The downside of Slack is that it's easy to lose track of all the notifications." The inbox "displays all open lines of communication between you and an agent"; "Right now items are sorted just by time". [LC-ambient](https://www.langchain.com/blog/introducing-ambient-agents)
- Agent Inbox contract: an interrupt carries `action_request` (shown as the item header), `config` flags `allow_ignore`, `allow_respond`, `allow_edit`, `allow_accept`, and a markdown `description`; the reply `type` is `accept`, `ignore`, `response` or `edit`. Repo "archived by the owner on Sep 20, 2026". [LC-inbox-repo](https://github.com/langchain-ai/agent-inbox) F·V
- `interrupt()`: "Graph waits indefinitely until you resume execution with a response."; on resume "the runtime restarts the entire node from the beginning", so "Side effects called before interrupt should (ideally) be idempotent." [LG-interrupts, n.d.](https://docs.langchain.com/oss/python/langgraph/interrupts) F·V
- Decision types, allowed per tool via `interrupt_on` ([LC-HITL, n.d.](https://docs.langchain.com/oss/python/langchain/human-in-the-loop.md) F·V):
  - approve: "Execute the tool with the original arguments as proposed by the agent."
  - edit: "Modify the tool arguments before execution."
  - reject: "Skip executing this tool call entirely and return rejection feedback to the agent."
  - respond: "Return the human's message directly as a synthetic tool result, skipping execution, for "ask user" style tools."
- Pitfalls: "Significant modifications to the original arguments may cause the model to re-evaluate its approach"; "Do not use `respond` to deny side-effecting tools, because its message is treated as a successful tool result." [LC-HITL](https://docs.langchain.com/oss/python/langchain/human-in-the-loop.md)
- Other deciders:
  - Claude Code auto mode: a classifier acts "as a substitute for a human approver"; after 3 consecutive or 20 total denials it hands back to the human. [Anth-auto, 2026-03-25](https://www.anthropic.com/engineering/claude-code-auto-mode) F·V
  - Codex, ChatGPT Work: "Auto-review sends eligible approval requests to a separate reviewer agent." [Auto-review, n.d.](https://learn.chatgpt.com/docs/sandboxing/auto-review) F·V
  - Jules: "Jules will eventually auto-approve the plan, which is set on a timer." [Jules-plan, n.d.](https://jules.google/docs/review-plan/) F·V
- Critique: one practitioner essay argues inbox-only products turn quick questions into runs and unwanted notifications; its numbers are unsourced. [TianPan, 2026-04-23](https://tianpan.co/blog/2026-04-23-async-agents-inbox-not-chat) F·I

### Inferences
- LangChain's "when to interrupt" is a design-time, per-tool policy; judge and classifier approaches decide per action at run time.

### Gaps
- Could not verify any independent study or first-hand report on Agent Inbox usage, notification volume or review latency. Queries: `"ambient agents" critique notification overload agent inbox experience report`; `LangChain agent inbox archived deprecated replaced Agent Builder inbox`.

## Across async agent products, what are the common ways of showing a plan before execution, showing progress, and packaging results for review? Which products require plan approval and which run then report?

### Takeaway
Hard plan gates are rare: Magentic-UI requires acceptance, Jules asks but auto-approves on a timer, Devin and Claude Code offer optional planning, and Cursor cloud agents, Manus, scheduled tasks and Pulse run then report. Approval has moved to consequential actions and sandbox boundaries, and results arrive as reviewable artifacts.

### Cited Findings
**Plan before execution**
- Mandatory gate: Magentic-UI (Accept button).
- Timed gate: "Once you submit a task, Jules will generate a plan. You can review and approve it before any code changes are made." ([Jules-start, n.d.](https://jules.google/docs/) F·V), then the timer applies. Since 2026-01-26 a "Planning Critic" reviews "all plans that do not require human intervention" ([Jules-changelog, 2026-10-29](https://jules.google/docs/changelog) F·V).
- Optional planning mode: Devin 2.0 "responds in seconds with relevant files, findings, and a preliminary plan" ([Devin2, 2025-04-03](https://cognition.com/blog/devin-2) F·V); today its Ask mode plans "without making changes to the actual code", then "Send to Devin" ([Devin-first-run, n.d.](https://docs.devin.ai/get-started/first-run.md) F·V). Claude Code: "Plan locally, execute in the cloud" ([CC-cloud, n.d.](https://code.claude.com/docs/en/claude-code-on-the-web) F·V).
- No plan gate documented: Cursor cloud agents, Manus ("Manus plans the task and runs each step in its sandbox." [Manus-quick, n.d.](https://manus.im/docs/introduction/quickstart.md) F·V), Operator, ChatGPT agent, scheduled tasks, Pulse.

**Progress, steering and results**
- Live computer view: Manus ([Manus-browser, n.d.](https://manus.im/docs/features/cloud-browser) F·V). A reviewer confirms its window "allows users not only to observe what the agent is doing but also to intervene at any point" and that "each session is replayable and shareable." ([MITTR, 2025-03-11](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/) F·I)
- Feeds and lists: Jules shows a real-time activity feed with mini diffs ([Jules-code, n.d.](https://jules.google/docs/code/) F·V). Devin merged Progress and Shell into one Activity view, groups sessions as Working / Ready / Blocked / Inactive, and added a notification inbox on 2026-10-07 ([Devin-relnotes, 2026-11-16](https://docs.devin.ai/release-notes/overview.md) F·V). "The Scheduled view acts as your inbox." ([Scheduled, n.d.](https://learn.chatgpt.com/docs/automations) F·V). ChatGPT Work collapses progress to a line such as "Worked for 1m 18s" ([SW-Work, 2026-08-30](https://simonwillison.net/2026/aug/30/understanding-chatgpt-work) F·I).
- Mid-run messages: Devin side chats can interrupt or be queued, and queued messages stay editable ([Devin-relnotes](https://docs.devin.ai/release-notes/overview.md)); Claude Code queues a message "until Claude reads it" ([CC-cloud](https://code.claude.com/docs/en/claude-code-on-the-web)); ChatGPT agent: "Users can interrupt, redirect, or pause a task at any time, with the agent picking up right where it left off." ([VB-agent, 2025-07-17](https://venturebeat.com/ai/openai-unveils-chatgpt-agent-that-gives-chatgpt-its-own-computer-to-autonomously-use-your-email-and-web-apps-download-and-create-files-for-you) F·V via press).
- Result packaging: Codex, "After about 8–10 minutes, the agent gives you back a diff." (OpenAI text quoted in [SW-Codex, 2025-05-16](https://simonwillison.net/2025/May/16/) F·V). "Cloud agents produce merge-ready PRs with artifacts (videos, screenshots, and logs)." ([Cursor-0224, 2026-02-24](https://cursor.com/changelog/02-24-26) F·V). Devin's test recording is "sent directly to you as an attachment" as a "quick sanity check" ([Devin-testing, n.d.](https://docs.devin.ai/work-with-devin/testing-and-recordings.md) F·V). Pulse writes "five to 10 briefs" overnight as cards and ends with "Great, that's it for today." ([TC-Pulse, 2025-09-25](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs/) F·V via press)

**Approval points**
- Consequential actions:
  - Operator asks "before finalizing actions that affect the state of the world (e.g., before completing a purchase or sending an email)". Watch mode: "we require that the user supervise Operator's actions by automatically pausing execution when the user becomes inactive or navigates away from the page." [Op-card, 2025-01-23, updated 2025-03-11](https://cdn.openai.com/operator_system_card.pdf) F·V
  - "ChatGPT Work will always ask for confirmation before consequential actions, such as submitting your information to book an appointment or completing a payment." [Work-browser, n.d.](https://learn.chatgpt.com/docs/browser) F·V
  - Manus prompts takeover for "complex verifications (SMS codes, CAPTCHA, multi-factor authentication)". [Manus-browser](https://manus.im/docs/features/cloud-browser)
- Sandbox boundary: "Codex asks for approval to edit files outside the workspace or to run commands that require network access."; the cloud agent phase "runs offline by default unless you enable internet access for that environment." ([Codex-security, n.d.](https://learn.chatgpt.com/docs/agent-approvals-security.md) F·V)
- No per-command approval: Cursor cloud "auto-runs all terminal commands, letting it iterate on tests", while its desktop agent "requires user approval for every command." ([Cursor-sec, n.d.](https://cursor.com/docs/cloud-agent/security-network) F·V). "Scheduled tasks run unattended and use your default sandbox settings." ([Scheduled](https://learn.chatgpt.com/docs/automations))
- Delegated to a model: Manus Studio's default mode, Approve for me, "Reviews and auto-approves safe local actions."; Ask for approval "Always asks for approval before local actions."; Full access "Runs local actions without approval." ([Manus-Studio, n.d.](https://manus.im/docs/features/desktop.md) F·V). Codex uses the same mode names ([Perm-modes, n.d.](https://learn.chatgpt.com/docs/permission-modes.md) F·V). Devin has an "Auto-approve actions on your behalf" setting, mechanism not described ([Devin-relnotes](https://docs.devin.ai/release-notes/overview.md)).
- Opt-in follow-on work: Devin tests after a PR only on request unless "Pre-approve testing" is on ([Devin-testing](https://docs.devin.ai/work-with-devin/testing-and-recordings.md)).

### Inferences
- From 2025 to 2026, per-action human prompts gave way to sandbox boundaries plus model reviewers, with the human gate at merge, send or pay.
- Proof of work is moving from logs to demonstrations, matching Magentic-UI participants' preference for visual checks.

### Gaps
- Could not verify whether Devin's Agent mode pauses for plan approval: the interactive-planning page now resolves to a tutorial index, and a 2024 wait-for-approval setting is snippet-only ([Devin-relnotes-2024](https://docs.devin.ai/release-notes/2024) S·V). Query: `Devin 2.0 interactive planning session docs approve plan`.
- Unverified recollection: ChatGPT agent narrates steps on screen; Codex cites terminal logs and test output.
- Could not verify Manus cloud-task confirmation rules or a current replay page. Query: `Manus "Manus's Computer" replay takeover to-do list docs how it works`.
- Pulse thumbs up/down and 24-hour expiry are snippet-only ([Pulse-post](https://openai.com/index/introducing-chatgpt-pulse/?so=1) S·V); its 2026 status could not be verified (the query did not run).

## What independent evidence exists about where these interaction models fail?

### Takeaway
Independent evidence is thin and small-scale: one hands-on Devin review, one Manus review, one browser-agent security disclosure and user complaints. The strongest numbers are vendors' own, on missed confirmations, rubber-stamped approvals and classifier misses.

### Cited Findings
- **Persisting on impossible work** (Devin): 20 tasks gave 3 successes, 14 failures, 3 inconclusive. "Devin would spend days pursuing impossible solutions rather than recognizing fundamental blockers." [AnswerAI, 2025-01-08](https://www.answer.ai/posts/2025-01-08-devin.html) F·I
- **Vendor's later account**: "67% of its PRs are now merged vs 34% last year"; "Devin handles clear upfront scoping well, but not mid-task requirement changes."; "It usually performs worse when you keep telling it more after it starts the task."; "When outcomes aren't straightforwardly verifiable, additional human review is necessary." [Devin-review, 2025-11-14](https://cognition.com/blog/devin-annual-performance-review-2025) F·V
- **Instability, shortcutting** (Manus): "frequent crashes and system instability"; the agent admitted it "got lazy"; "It has a higher failure rate than ChatGPT DeepResearch" (attributed to Manus's chief scientist). [MITTR](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/)
- **Approval fatigue and over-asking**: "in practice users accept 93% of them anyway."; "Over time that leads to approval fatigue, where people stop paying close attention to what they're approving." The replacement classifier misses 17% of real overeager actions (n=52) at a 0.4% false-positive rate (n=10,000) and is "not a drop-in replacement for careful human review on high-stakes infrastructure." ([Anth-auto](https://www.anthropic.com/engineering/claude-code-auto-mode)). Magentic-UI participants judged cart approval unnecessary ([MUI-paper](https://arxiv.org/html/2507.22358v1)).
- **Missed confirmations**: unmitigated Operator made 13 errors in 100 prompts, 5 "to some degree, irreversible or possibly severe"; confirmations "reduced the risk by approximately 90%"; confirmation recall was 92% on 607 tasks; it over-refused (not_overrefuse 55% vs 90% for GPT-4o). [Op-card](https://cdn.openai.com/operator_system_card.pdf)
- **Prompt injection**: Operator susceptibility was 23% "compared to 62% with no mitigations" ([Op-card](https://cdn.openai.com/operator_system_card.pdf)). Comet "feeds a part of the webpage directly to its LLM without distinguishing between the user's instructions"; Brave demonstrated account takeover and later judged the fix incomplete ([Brave, 2025-08-20](https://brave.com/blog/comet-prompt-injection/) F·I). Willison says Work "combines all three" lethal-trifecta elements ([SW-Work](https://simonwillison.net/2026/aug/30/understanding-chatgpt-work)). Cursor: "Auto-running introduces data exfiltration risk" ([Cursor-sec](https://cursor.com/docs/cloud-agent/security-network)).
- **Review burden**: long task histories overwhelmed Magentic-UI participants, who asked for visual summaries. [MUI-paper](https://arxiv.org/html/2507.22358v1)
- **Notification backlog**: "If you don't respond to a few, the a backlog of slack notifications grows." ([LC-ambient](https://www.langchain.com/blog/introducing-ambient-agents)). Devin later added per-type switches and "failure notifications are sent on a backoff" ([Devin-relnotes](https://docs.devin.ai/release-notes/overview.md)).
- **Lost waiting state**: a Claude Code cloud session "counts as inactive while it waits for you to approve an MCP connector tool call ... and it can expire during that wait". [CC-cloud](https://code.claude.com/docs/en/claude-code-on-the-web)
- **Abrupt removal**: one user reports agent mode vanished with "no meaningful advance notice, deprecation period, migration guide, or explanation." [OAI-forum, 2026-08-08](https://community.openai.com/t/agent-mode-was-removed-with-no-real-replacement/1389601) F·I

### Inferences
- Three failure classes recur: humans stop reading approvals; agents fail to ask or persist on a dead end; review cost grows with trace length.

### Gaps
- Could not verify any peer-reviewed 2025–26 study of review burden, stale plans or notification load for async agents. Query: `agent approval fatigue users approve permission prompts percent study rubber-stamp human-in-the-loop 2025 2026`. A later "97%" approval figure appeared in snippets only.
- Incident reports (agents deleting data) were not traced to primary sources.

## Which patterns have vendors abandoned or changed and what reasons did they give?

### Takeaway
Between mid-2025 and late 2026 several flagship surfaces were withdrawn or merged: Operator, ChatGPT agent mode, Jules and the standalone Agent Inbox. Stated reasons rarely go beyond consolidation.

### Cited Findings
| Product | Change | Date | Reason stated | Source |
|---|---|---|---|---|
| Operator | Merged into ChatGPT agent; standalone site ended | 2025-07-17; about 2025-08-31 (end date from third-party snippets) | "so we brought the best of both together" | [VB-agent](https://venturebeat.com/ai/openai-unveils-chatgpt-agent-that-gives-chatgpt-its-own-computer-to-autonomously-use-your-email-and-web-apps-download-and-create-files-for-you); [Operator-post](https://openai.com/blog/introducing-operator) S·V |
| ChatGPT agent mode | Removed; users pointed to ChatGPT Work (announced 2026-07-09) | reported 2026-08 | None seen. Support: Work "now has a separate cloud browser that can navigate interactive sites and pause for sign-in or takeover on supported accounts." | [OAI-forum](https://community.openai.com/t/agent-mode-was-removed-with-no-real-replacement/1389601); [SW-Work](https://simonwillison.net/2026/aug/30/understanding-chatgpt-work) |
| Atlas, Codex app | Atlas browser sunset; Codex desktop app merged into one ChatGPT app (Chat, Work, Codex) | 2026-07-09 | "building on lessons learned from Atlas and from the people who used it" (as quoted) | [PPC, 2026-07-13](https://ppc.land/openai-kills-atlas-browser-folds-it-into-new-chatgpt-work-agent/) F·V via press |
| ChatGPT Tasks | Beta option "4o with scheduled tasks" became a Scheduled inbox with Gmail, Slack and GitHub triggers | 2025-01-14 to 2026 | Not stated | [TC-Tasks, 2025-01-14](https://techcrunch.com/2025/01/14/chatgpt-now-lets-you-schedule-reminders-and-recurring-tasks/) F·V via press; [Scheduled](https://learn.chatgpt.com/docs/automations) |
| Jules | "Jules will wind down on December 31, 2026."; read-only after 2026-11-11 | announced 2026-10-29 | "as part of our work to unify our agentic coding efforts"; "it was an experiment to learn how asynchronous coding agents could help you tackle your backlog and ship faster." Successor named: Google Antigravity | [Jules-changelog](https://jules.google/docs/changelog) |
| LangChain Agent Inbox | Repo archived; LangSmith Fleet has "The Inbox gives you human-in-the-loop oversight across all of your agents." | 2026-09-20 | Not stated | [LC-inbox-repo](https://github.com/langchain-ai/agent-inbox); [LC-Fleet, 2026-03-19](https://www.langchain.com/blog/introducing-langsmith-fleet) F·V |
| Magentic-UI | 0.1 became MagenticLite 0.2 for small models | 21 May (year not shown) | "redesigned to do more with less" | [README-main](https://raw.githubusercontent.com/microsoft/magentic-ui/main/README.md) |
| Devin | "The separate Tasks tab is retired."; "Workspace tabs no longer open on their own as Devin works." | 2026-10 to 2026-11 | Not stated | [Devin-relnotes](https://docs.devin.ai/release-notes/overview.md) |
| Cursor | "Cloud Agents were formerly called Background Agents."; Agents Window ("Cursor's agent-first interface") shipped with Cursor 3 | 2026-04-02 | The window "helps pull you up to a higher level of abstraction" | [Cursor-cloud, n.d.](https://cursor.com/docs/cloud-agent) F·V; [Cursor-AW, n.d.](https://cursor.com/docs/agent/agents-window) F·V |
| Claude Code | Auto mode replaces manual permission prompts | 2026-03-25 | Approval fatigue (93% accepted) | [Anth-auto](https://www.anthropic.com/engineering/claude-code-auto-mode) |

### Inferences
- The withdrawn surfaces centre on watching an agent drive a browser (Operator, agent mode, Atlas) or on a single-purpose async tool (Jules, Agent Inbox); replacements bundle chat, async tasks and scheduled runs in one workspace. Vendors do not say this.
- Devin's late-2026 changes cut default live detail, consistent with attention cost acting as a design constraint.

### Gaps
- OpenAI's own retirement notices were not read (403). The agent-mode removal date rests on one forum thread and snippets ([agent-retired](https://omidsaffari.com/blog/chatgpt-agent-retired) S·I); the Atlas end date of 2026-08-09 is snippet-only ([Atlas-retire](https://letsdatascience.com/news/openai-shutters-standalone-chatgpt-atlas-desktop-browser-0cc642c2) S·I).

## Comparison table and recurring patterns

Status as of each source's date; quotes for approval points are in the sections above.

| Product | Unit of work | How work is shown | Steering | Approval points | Evidence of work | Source |
|---|---|---|---|---|---|---|
| Magentic-UI (2025) | Session with editable plan | Plan editor, live browser, status dot | Pause, chat, browser takeover | Plan accept; guard on irreversible actions | Steps, screenshots, answer | [MUI-paper](https://arxiv.org/html/2507.22358v1) V |
| LangGraph, Agent Inbox | Interrupted thread | Inbox of pending interrupts, by time | Edit arguments, respond | Developer-set per tool: approve, edit, reject, respond | Action, arguments, description | [LC-HITL](https://docs.langchain.com/oss/python/langchain/human-in-the-loop.md) V; [LC-inbox-repo](https://github.com/langchain-ai/agent-inbox) V |
| Devin | Session (Ask or Agent); child sessions | Chat, Activity view, task drawer, artifacts rail, notification inbox | Queued messages, side chats, IDE | Approval cards (credentials, approvals, network); test opt-in; auto-approve option | PR, annotated test video | [Devin-relnotes](https://docs.devin.ai/release-notes/overview.md) V; [Devin-testing](https://docs.devin.ai/work-with-devin/testing-and-recordings.md) V |
| Codex cloud, ChatGPT Work | Task | Collapsed status line, file cards | Follow-ups, change direction | Sandbox boundary; confirm before consequential actions; reviewer agent | Diff, PR, files | [Codex-cloud, n.d.](https://learn.chatgpt.com/docs/cloud) F·V; [Work-start, n.d.](https://learn.chatgpt.com/docs/get-started-with-work) F·V; [SW-Work](https://simonwillison.net/2026/aug/30/understanding-chatgpt-work) I |
| Jules (ends 2026-12-31) | Task | Plan, activity feed, mini diffs | Chat; pause, resume | Plan approval with auto-approve timer; publish | Diff, summary, screenshots, PR | [Jules-plan](https://jules.google/docs/review-plan/) V; [Jules-code](https://jules.google/docs/code/) V; [Jules-changelog](https://jules.google/docs/changelog) V |
| Cursor cloud agents | Agent with own VM and branch | Agents Window, web list, remote desktop | Follow-ups, desktop takeover | None per command; network allowlist; merge | PR with video, screenshots, logs | [Cursor-cloud](https://cursor.com/docs/cloud-agent) V; [Cursor-sec](https://cursor.com/docs/cloud-agent/security-network) V |
| Manus | Task (credits) | Live computer view, run updates | Follow-up, branch, takeover | Takeover on verification; Studio permission modes | Report, slides or site; replay | [Manus-quick](https://manus.im/docs/introduction/quickstart.md) V; [Manus-browser](https://manus.im/docs/features/cloud-browser) V; [Manus-Studio](https://manus.im/docs/features/desktop.md) V; [Manus-auto, n.d.](https://manus.im/docs/automations.md) F·V; [MITTR](https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/) I |
| Operator (2025) | Browser task | Live remote browser | Take control | Confirm state-changing actions; watch mode; refusals | Screenshots | [Op-card](https://cdn.openai.com/operator_system_card.pdf) V; [SW-Operator, 2025-01-23](https://simonwillison.net/2025/Jan/23/introducing-operator/) F·I |
| ChatGPT agent (2025–26) | Agent task in a chat | Visual browser on a virtual computer | Interrupt, redirect, pause | Confirmation prompts; watch mode; refuses financial transfers | Files, slides | [VB-agent](https://venturebeat.com/ai/openai-unveils-chatgpt-agent-that-gives-chatgpt-its-own-computer-to-autonomously-use-your-email-and-web-apps-download-and-create-files-for-you) V via press |
| ChatGPT scheduled tasks | Scheduled task and its runs | Scheduled view as inbox | Update by chat; run now | Runs unattended within sandbox settings | New chat per run | [Scheduled](https://learn.chatgpt.com/docs/automations) V |
| ChatGPT Pulse (2025) | Card (brief) | Daily set of cards | Feedback, topic requests | None; read-only briefs | Expandable report | [TC-Pulse](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs/) V via press |
| Claude Code cloud sessions | Cloud session | Session sidebar, Changes card | Queued messages, teleport to terminal | Permission mode; asks on ambiguous PR feedback | Diff with inline comments, PR | [CC-cloud](https://code.claude.com/docs/en/claude-code-on-the-web) V |

Recurring patterns:
1. Plan preview before running: Magentic-UI (mandatory), Jules (timer), Devin, Claude Code (optional).
2. Confirmation before consequential actions: Magentic-UI, Operator, ChatGPT agent, ChatGPT Work, LangGraph review.
3. Sandbox boundary instead of per-action prompts: Codex, Cursor, Jules, Claude Code.
4. Model as approver with human escalation: Magentic-UI ActionGuard, Codex and Manus "Approve for me", Claude Code auto mode, Jules critics.
5. Takeover and hand-back of the agent's computer (logins, CAPTCHAs, manual testing): Magentic-UI, Operator, ChatGPT Work, Manus, Cursor.
6. Eyes-on supervision on sensitive sites: Operator, ChatGPT agent.
7. Task list or inbox with a needs-input state: Magentic-UI, Agent Inbox and Fleet, Devin, ChatGPT Scheduled, Cursor, Manus, Claude Code.
8. Live view of the agent's computer: Manus, Operator, Magentic-UI, Cursor.
9. Result as reviewable artifact: Codex, Jules, Cursor, Devin, Claude Code (diff or PR); Manus, ChatGPT Work (files).
10. Demonstration as proof: Cursor, Devin, Jules, Magentic-UI.
11. Replay or shareable run: Manus, Cursor, Claude Code.
12. Scheduled or event-triggered runs reporting to a feed: ChatGPT Scheduled, Manus Automations, Devin Automations, Jules scheduled tasks, Claude Code routines, Pulse.
13. Learning from past runs: Magentic-UI plan gallery, Jules memory, Devin Knowledge and Skills ([Devin-index](https://docs.devin.ai/_llms/en/cloud.txt) F·V).
14. Queued messages and side chats during a run: Devin, Claude Code.
15. Local-to-cloud handoff: Cursor ([Cursor-3.7, 2026-06-17](https://cursor.com/changelog/cloud-in-agents-window) F·V), Claude Code teleport.
16. Digest that ends on purpose: Pulse.
