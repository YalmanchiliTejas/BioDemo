# Agent interaction design evidence: generative UI and agent design guidance (status as of 2026-11-16)

Tags. **F** = FETCHED (opened, passage read); **S** = SNIPPET (search result only); **V** = vendor documentation/claim; **I** = independently evidenced; **O** = expert/practitioner opinion; n.d. = no date on page (read 2026-11-16). Quotes are verbatim as returned by page extraction (PDFs: extracted text, ligature spacing normalised).

## 1. What are A2UI and AG-UI exactly, how do they differ, what is their maturity, and what problem does each solve?

### Takeaway
A2UI is a declarative UI payload: the agent emits JSON naming components from a client-owned catalog and the client renders them natively. AG-UI is the event/state transport between agent and app, and can carry A2UI, MCP Apps or custom UI. Both reached 1.0 only in autumn 2026 (AG-UI 2026-09-30, A2UI 2026-11-11).

### Cited Findings
**A2UI (Google, Apache-2.0)**
- Definition: "an open-source generative UI framework that enables agents to select, compose, or build experiences" — [a2ui.org n.d.](https://a2ui.org/) F·V; at launch "a format optimized for representing updateable, agent-generated UIs" — [Google 2025-12-15](https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/) F·V.
- Problem (launch post): a remote agent "cannot touch your UI directly; it must send messages"; iframe-sandboxed HTML is called heavy and visually disjointed (paraphrase).
- How: messages `createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`; flat component list linked by ID references; user `action` messages return to the agent; transport-agnostic — [spec v1.0](https://a2ui.org/specification/v1.0-a2ui/) F·V.
- Who renders: "The client owns the rendering." (launch post). Catalog: "You define the components and functions your client can render in `catalog.json`."; the SDK validates model output against it — [concepts n.d.](https://a2ui.org/concepts/overview/) F·V.
- Security: "safe like data, but expressive like code"; "a declarative data format, not executable code"; "trusted, pre-approved UI components" (launch post).
- Status: "Our format is currently at v0.8" (2025-12-15); "the first stable version of our open protocol for generative UI" — [Google 2026-11-11](https://developers.googleblog.com/a2ui-10-build-delightful-fast-reliable-agentic-experiences/) F·V; [roadmap n.d.](https://a2ui.org/roadmap/) F·V lists v1.0 Current, v0.9.1/v0.9 Previous, v0.8 Deprecated. Conflicts: the spec page says "Last Updated: Jun 8, 2026"; search snippets of that roadmap page (S) still showed v1.0 as "Candidate"; the Compose renderer is "currently v0.9.1, and v1.0 coming soon".
- Adopters (vendor-named, unverified): Atlassian Jira, Alation, ByteDance Lynx, Gemini Enterprise (2026-11-11 post); 17.5k stars — [repo](https://github.com/google/A2UI) F. In 1.0, generated HTML and JS "can run as an MCP App inside an A2UI surface, next to your native components" (a2ui.org).

**AG-UI (CopilotKit, MIT)**
- "AG-UI is an open, lightweight, event-based protocol that standardizes how AI agents connect to user-facing applications."; "born from CopilotKit's initial partnership with LangChain and CrewAI" — [docs n.d.](https://docs.ag-ui.com/introduction) F·V. Announced [2025-05-12](https://www.copilotkit.ai/blog/introducing-ag-ui-the-protocol-where-agents-meet-users) F·V.
- Events: "AG-UI 1.0 defines 31 event types in eight families." — [README](https://github.com/ag-ui-protocol/ag-ui) F·V: lifecycle (RunStarted, RunFinished, RunError, StepStarted, StepFinished), text message, tool call, state, activity, subagent, reasoning, special (Raw, Custom) — [events n.d.](https://docs.ag-ui.com/concepts/events) F·V.
- Shared state: StateSnapshot "Provides a complete snapshot of an agent's state."; StateDelta "Provides a partial update to an agent's state using JSON Patch." (events).
- Human-in-the-loop: RunFinished `outcome` type `interrupt` means "the run paused for human input" and the client resumes with a new run (events); "Pause, approve, edit, retry, or escalate mid flow without losing state." (docs).
- Maturity: 1.0 on [2026-09-30](https://www.copilotkit.ai/blog/ag-ui-1.0) F·V: "a stable specification that lays out clear rules for every event"; "AG-UI 1.0 is backwards compatible". Vendor claim: "adopted by Google, Microsoft, Amazon and Oracle". 19.2k stars; HTTP+SSE and HTTP+Protobuf bindings (README).
- Difference: AG-UI is "an event/state protocol" that is "not a UI specification" — [CopilotKit guide 2026-01-29](https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026) F·V; Google calls the two "complementary" (launch post).

**Other approaches**
- Vercel AI SDK: the model calls a tool and "This data can then be passed to a React component for rendering."; components are developer-written; page refers to AI SDK 5.0 — [docs n.d.](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces) F·V. History: `streamUI` "calls a model and allows it to respond with React Server Components", but "AI SDK RSC is currently experimental. We recommend using AI SDK UI for production." — [RSC n.d.](https://ai-sdk.dev/docs/ai-sdk-rsc/overview) F·V; "It is not possible to abort a stream using server actions." — [migration guide n.d.](https://ai-sdk.dev/docs/ai-sdk-rsc/migrating-to-ui) F·V.
- MCP Apps: SEP-1865 "authored by MCP Core Maintainers at OpenAI and Anthropic" with MCP-UI's creators; "UI templates are resources with the `ui://` URI scheme, referenced in tool metadata."; "supports only `text/html` content" — [MCP blog 2025-11-21](https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/) F·V. "MCP Apps are now live as an official MCP extension"; "When a tool declares a UI resource, the host renders it in a sandboxed iframe." — [MCP blog 2026-01-26](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) F·V. Clients listed: Claude, VS Code GitHub Copilot, Microsoft 365 Copilot, Goose, Postman — [MCP docs n.d.](https://modelcontextprotocol.io/docs/extensions/apps) F·V. "MCP-UI is now standardized into MCP Apps!" — [mcpui.dev n.d.](https://mcpui.dev/) F·V.
- OpenAI Apps SDK: its URL now serves "Plugins" docs — [OpenAI n.d.](https://developers.openai.com/apps-sdk/) F·V. "ChatGPT implements the open MCP Apps standard"; "UI runs in an isolated iframe." — [UI guide n.d.](https://developers.openai.com/plugins/build/chatgpt-ui.md) F·V. "ChatGPT is now fully compatible with the MCP Apps spec." (2026-02-22) — [changelog](https://developers.openai.com/plugins/changelog) F·V. 2025 preview launch: S only — [TestingCatalog](https://www.testingcatalog.com/openai-launches-chatgpt-apps-and-sdk-preview-outside-eu).
- Artifacts/canvas (model writes a document or code; vendor app renders it beside chat). Claude creates one when "It's significant and self-contained, typically over 15 lines." — [Claude support, "Updated this week"](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) F·V; GA 2024-08-27 — [Anthropic](https://www.anthropic.com/news/artifacts) S. Gemini: "Canvas is a new interactive space within Gemini designed to make creating, refining and sharing your work easy." — [Google 2025-03-18](https://blog.google/products/gemini/gemini-collaboration-features/) F·V. ChatGPT canvas, 2024-10-03 — [OpenAI](https://openai.com/index/introducing-canvas/) S (HTTP 403 on fetch).

**Three tiers** (CopilotKit guide, F·V)
- Static: "The frontend owns the UI."; the agent picks a predefined component and supplies data.
- Declarative: the agent returns a structured spec, rendered "with its own constraints and styling" (A2UI).
- Open-ended: the agent returns a full UI surface; "you trade consistency and safety for flexibility."
- Practitioner view: full generation is "the demo everyone admires and nobody can ship" — [J. Hall 2026-06-04](https://dev.to/joshjhall/generative-ui-is-three-things-only-one-ships-n66) F·O.

### Inferences
- A2UI answers "what to show"; AG-UI answers "how agent and app exchange events, state and approvals". They compose.
- MCP Apps UI is developer-authored and pre-declared, not model-written at runtime; CopilotKit still files it under "open-ended" because the host does not control its markup.
- "Stable" is weeks old for both; renderer support lags the spec.

### Gaps
- No independent adoption or reliability data for either protocol.
- ChatGPT "Intelligent UI": only a competitor's description (ChatGPT "creates interfaces on demand") — [CopilotKit 2026-10-09](https://www.copilotkit.ai/blog/introducing-open-intelligent-ui) F·V. Could not verify from OpenAI. Queries: `OpenAI Apps SDK renamed "plugins" ChatGPT 2026 MCP Apps "Intelligent UI"` (no mention); `ChatGPT "Intelligent UI" OpenAI launch generated interface 2026` (not run: session search budget exhausted).
- Apps SDK launch date (2025-10-06) and AI SDK RSC release history: unverified recollection. Artifacts/canvas sandbox details: not in pages fetched.

## 2. What empirical evidence exists that generated interfaces outperform or underperform chat/markdown or hand-built UI, and under what conditions?

### Takeaway
Two studies show strong one-shot preference for generated UI over text/markdown, but below expert-built pages, with latency excluded, and with a far narrower margin on users' own queries. Nothing found measures repeated use, learnability, task accuracy or accessibility.

### Cited Findings
| Study | Design | Result | Caveats stated |
|---|---|---|---|
| Google, "Generative UI: LLMs are Effective UI Generators" — [arXiv 2604.09577v1, submitted 2026-02-24](https://arxiv.org/html/2604.09577) F; [blog 2025-11-18](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/) F. Vendor-authored preprint | 100 LMArena prompts (8 removed); pairwise preference; 2 raters per result; raters undescribed; pre-cached outputs | ELO: expert site 1800.3; generative UI 1736.2; markdown 1437.7; top search result 1352.2; text 1173.7. Generative UI preferred vs markdown 82.8%, vs text 97.0%, vs expert site 35.3%; "at least comparable in 50% of cases" | "when ignoring generation speed"; generation "can often take a minute or two"; Gemini 2.0 Flash erred on 29% of outputs, Flash-Lite 60% |
| Stanford SALT, "Generative Interfaces for Language Models" — [arXiv 2508.19227v3, 2026-05-01, ACL 2026 Findings](https://arxiv.org/html/2508.19227v3) F·I | 100 synthetic queries, 10 domains; Prolific; 3 annotators per item; 428 annotators; Fleiss' kappa 0.525 | Generated vs chat (Claude 3.7): 84% / 4% tie / 12%; vs GPT-4o chat 69/1/30. Data analysis 93.8%; advanced AI/ML 50.0%; detailed queries 80%, concise 73% | Abstract: "up to a 72% improvement in human preference"; latency "of up to several minutes" |
| Same paper, real users | 76 participants, 380 own queries | Generated 50.8% win, 8.2% tie, 41.1% loss; 30.3% strongly preferred generated, 18.4% chat | Chat preferred for easy how-to and maths; "Chatbot interface is most people know already, while GenUI is a somewhat complex and unfamiliar app." |
| NN/g — [2024-03-22](https://www.nngroup.com/articles/generative-ui/) F·O | Expert essay, no data | "Constantly changing UIs will cause usability problems."; "This constant relearning of the interface might cause frustration" | Speculative; also sees "immense potential to improve accessibility and inclusivity" |
| Thesys — [n.d.](https://www.thesys.dev/report) F·V | "A study with 145 people from 5 countries" | Qualitative claims only | Vendor-run; method undisclosed |
| Suh et al. — [arXiv 2503.15885, 2025-03-20](https://arxiv.org/abs/2503.15885) F·I (preprint) | LLM vs human web code | "LLMs often produce more accessible code", "but struggle with complex issues such as ARIA attributes" | Static code, not runtime UI |

### Inferences
- Evidence favours generated UI for information-dense, exploratory, visual tasks; it weakens for short factual, how-to and maths queries.
- Both studies measure first-impression preference between cached outputs, not completion, errors or return visits, so results do not transfer directly to daily-use work tools.
- Curated queries (84/12) versus real queries (50.8/41.1) suggests benchmarks overstate benefit.

### Gaps
- No study found on consistency across sessions, learnability or muscle memory. Query `generative UI user study consistency learnability dynamically generated interfaces usability 2025 arXiv` returned preference studies only (e.g. AlignUI, [arXiv 2601.17614](https://arxiv.org/html/2601.17614), S).
- Accessibility of runtime-generated UI: could not verify; query `study accessibility of LLM-generated user interfaces WCAG violations generated web UI code empirical 2025` not run (budget).
- No comparison of catalog UI (A2UI) with fully generated UI.
- arXiv ID 2604 versus stated submission 2026-02-24 is unexplained; a search snippet of the [arXiv PDF](https://arxiv.org/pdf/2604.09577) (S) reported ELO 1710.7; the fetched HTML shows 1736.2.

## 3. What known risks do sources identify for agent-composed UI?

### Takeaway
Sources name inconsistency, relearning and code-execution risk explicitly (latency: section 2). Accessibility is asserted both ways without data. No source addresses reproducing what a user saw.

### Cited Findings
| Risk | Source states | Source |
|---|---|---|
| Inconsistency | "Rendering arbitrary UI introduces security and performance concerns, inconsistent styling"; "consistency is a property of the sequence of interactions, not any one of them" | CopilotKit guide F·V; Hall F·O |
| Learnability, muscle memory | "Most of what a user touches needs to be predictable enough that they build muscle memory and stop seeing the chrome."; NN/g and Stanford quotes above | Hall F·O; NN/g; Stanford |
| Unneeded UI | Interfaces generated for all queries, even when interaction is unnecessary (paraphrase) | Stanford F·I |
| Executing generated or third-party code | "Iframe sandboxing: All UI content runs in sandboxed iframes with restricted permissions"; "Hosts can require explicit approval for UI-initiated tool calls"; render `structuredContent` "and treat it as untrusted input" | MCP blog, OpenAI UI guide F·V |
| Accessibility | Possible accessibility barriers (ethics note, paraphrase); A2UI 1.0 adds accessibility support (paraphrase) | Stanford F·I; Google 2026-11-11 F·V |
| Misplaced trust | Overconfidence from polished presentation (paraphrase) | Stanford F·I |
| Auditability | "Auditable messages: All UI-to-host communication goes through loggable JSON-RPC"; "Predeclared templates: Hosts can review HTML content before rendering" | MCP blog 2025-11-21 F·V |

### Inferences
- Catalog and pre-declared-template approaches make rendered UI reviewable in advance; fully generated UI does not. Logging the payload is the only route to reconstructing what a user saw.

### Gaps
- No source covers archiving the exact interface a user acted on; no production incident or error-rate data for generated UI.

## 4. What specific rules do Linear, GitHub, Notion, Anthropic, Microsoft, Google and OpenAI publish?

### Takeaway
All seven converge on scoped permissions, visible state, human confirmation for irreversible actions and a human who stays answerable. They differ on how often to ask and whose identity the agent wears.

### Cited Findings
**Linear** (F·V)
- [Agent Interaction Guidelines n.d.](https://linear.app/developers/aig): "The agent must signal its identity clearly so that it can never be mistaken for a person."; inhabit the platform natively; "When invoked, an agent should provide immediate, but unobtrusive, feedback."; humans can "inspect the underlying reasoning, tool calls, prompts, and decision logic"; "When asked to disengage, an agent should step back, immediately."; "An agent can carry out tasks, but the final responsibility should always remain with a human."
- Delegation: "Assigning an issue to your app now sets it as the `delegate`, not the `assignee`."; "humans maintain ownership while agents act on their behalf"; "Agents cannot be added as project members or set as project leads." — [developers/agents n.d.](https://linear.app/developers/agents). Launched [2025-05-20](https://linear.app/changelog/2025-05-20-linear-for-agents).
- Sessions: "Agent sessions can have one of 6 states: `pending`, `active`, `error`, `awaitingInput`, `complete`, `stale`."; answer the webhook "within 5 seconds"; send an activity "within 10 seconds to avoid the session being marked as unresponsive". Activity types: thought, elicitation, action, response, error — [agent-interaction n.d.](https://linear.app/developers/agent-interaction).
- Stop signal: "From the moment this signal is received, the agent must not perform any further actions"; `auth` and `select` signals go agent-to-human — [signals n.d.](https://linear.app/developers/agent-signals). "move the issue to the first status in `started` when your agent begins work" — [best practices n.d.](https://linear.app/developers/agent-best-practices).

**GitHub** (F·V)
- Renamed "Copilot cloud agent"; works in the background; "session logs show the work and tools used."; "Logs do not replace your own review and testing." — [about n.d.](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent). Started from issues, agents tab, Chat, CLI, MCP server, Slack, Teams, Linear, Jira — [starting sessions n.d.](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/assign-copilot-to-an-issue).
- Guardrails: "Only users with write access to the repository can trigger Copilot cloud agent to work."; "a new `copilot/` branch is created for Copilot, and the agent can only push to that branch"; "Draft pull requests created by Copilot cloud agent must be reviewed and merged by a human."; it "Prevents the user who asked Copilot cloud agent to create a pull request from approving it."; workflows wait for "Approve and run workflows"; "Copilot cloud agent's commits are authored by Copilot", requester co-author, signed, linked to session logs; hidden characters are filtered from input (paraphrase) — [risks and mitigations n.d.](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations).
- Agent HQ: mission control is "a single command center to assign, steer, and track the work of multiple agents from anywhere" — [GitHub 2025-10-28](https://github.blog/news-insights/company-news/welcome-home-agents/). Guidance: "Don't wait until the agent finishes to provide feedback."; you can "stop an agent mid-task and give it refined instructions" — [GitHub 2025-12-01](https://github.blog/ai-and-ml/github-copilot/how-to-orchestrate-agents-using-mission-control/).
- Copilot Workspace: "Everything that GitHub Copilot Workspace proposes—from the plan to the code—is fully editable, allowing you to iterate until you're confident in the path ahead." — [GitHub 2024-04-29](https://github.blog/news-insights/product-news/github-copilot-workspace/). Preview sunset 2025-05-30 — [GitHub Next](https://githubnext.com/projects/copilot-workspace) S (page body not retrievable).

**Notion** (F·V)
- Notion Agent ([3.0, 2025-09-18](https://www.notion.com/releases/2025-09-18)): "Notion Agent has the same permissions you do. If you can't view or edit specific content, your agent can't either."; in Slack it "acts as you, so anything it posts shows up as coming from you" — [help n.d.](https://www.notion.com/help/notion-agent).
- Approval modes: Always ask "Asks you before every action that changes content or uses a connected app"; Review for me (default) "Works on its own to review actions for you, and asks when an action is potentially unsafe"; Skip all approvals "Runs every action without asking" (admins can disable). Undo: ask the agent, restore page history, or fix connected-app actions in that app — [approvals n.d.](https://www.notion.com/help/choose-how-notion-agent-asks-for-your-approval).
- Custom Agents ([3.3, 2026-02-24](https://www.notion.com/releases/2026-02-24)): "Every run is logged, so changes are visible and reversible."; triggers: schedule, Notion events, Slack events, @mentions; "Agents act only on the pages, databases, and external apps you explicitly grant access to." — [help n.d.](https://www.notion.com/help/custom-agents). "A Custom Agent responds using the agent's own access, not the permissions of the person who triggered it."; "Agent users can retrieve information from resources they lack access to" — [sharing n.d.](https://www.notion.com/help/custom-agents-sharing-and-permissions).

**Anthropic** (F·V; figures are first-party)
- "finding the simplest solution possible, and only increasing complexity when needed"; "Agents can then pause for human feedback at checkpoints or when encountering blockers."; "stopping conditions (such as a maximum number of iterations)"; "Prioritize transparency by explicitly showing the agent's planning steps." — [Building effective agents 2024-12-19](https://www.anthropic.com/engineering/building-effective-agents).
- Claude Code has "read-only permissions by default"; "humans should retain control over how their goals are pursued, particularly before high-stakes decisions are made"; users can stop and redirect Claude at any time (paraphrase) — [framework 2025-08-04](https://www.anthropic.com/news/our-framework-for-developing-safe-and-trustworthy-agents).
- Modes: default (reads only), acceptEdits, plan, auto, dontAsk, bypassPermissions ("Only use this mode in isolated environments"); "if the classifier blocks an action 3 times in a row or 20 times total, auto mode pauses and Claude Code resumes prompting" — [permission modes n.d.](https://code.claude.com/docs/en/permission-modes).
- Users accept 93% of permission prompts; "approval fatigue, where people stop paying close attention to what they're approving"; classifier false positives 0.4% (n=10,000), false negatives 17% (n=52 real overeager actions) — [auto mode 2026-03-25](https://www.anthropic.com/engineering/claude-code-auto-mode). "sandboxing safely reduces permission prompts by 84%" — [sandboxing 2025-10-20](https://www.anthropic.com/engineering/claude-code-sandboxing).
- "Among new users, roughly 20% of sessions use full auto-approve, which increases to over 40% as users gain experience."; 0.8% of actions appear irreversible; requiring approval of every action "will create friction without necessarily producing safety benefits" — [Measuring agent autonomy 2026-02-18](https://www.anthropic.com/research/measuring-agent-autonomy).

**Microsoft** (F·V; HAX is peer-reviewed, CHI 2019)
- "Agent status, or what the agent is doing, is clearly visible at all times."; an agent "largely operates in the background and only nudges us when it is relevant and appropriate"; "A certain level of Agent uncertainty is expected." — [UX design for agents 2025-04-11](https://microsoft.design/articles/ux-design-for-agents/).
- HAX: "Support efficient dismissal."; "Support efficient correction."; "Scope services when in doubt."; "Make clear why the system did what it did." — [Microsoft Research 2019-02-01](https://www.microsoft.com/en-us/research/blog/guidelines-for-human-ai-interaction-design/).
- Copilot Studio: "Before an agent deletes or overwrites data, sends information, or performs another irreversible action, require user confirmation or an authorized human review."; "Instructions alone aren't a guarantee that execution stops." — [agentic loops 2026-11-05](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/agentic-loops-in-practice). "Maintain detailed logs of everything the agent does"; least-privileged access — [autonomous agents 2026-11-05](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/autonomous-agents). "Ensure that users know they're using an agent that uses generative AI capabilities." — [responsible AI 2026-01-16](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/responsible-ai).

**Google** (F·V)
- "Every agent must have a well-defined set of controlling human user(s)."; systems must "reliably distinguish instructions originating from an authorized controlling user versus any other input"; "For actions deemed critical or irreversible—such as deleting large amounts of data, authorizing significant financial transactions, or changing security settings—the system should require explicit human confirmation before proceeding"; powers "must be carefully limited"; actions and planning "must be observable and auditable" — [Secure AI Agents, May 2025](https://storage.googleapis.com/gweb-research2023-media/pubtools/1018686.pdf).
- Chrome's agent confirms before "completing a purchase or payment, sending messages"; "details each step in a work log"; "The user can pause to take over or stop a task at any time." — [Google 2025-12-08](https://blog.google/security/architecting-security-for-agentic/).
- PAIR Guidebook (n.d.): "When an AI system fails, often the easiest path forward is to let the user take over." — [Errors](https://pair.withgoogle.com/chapter/errors-failing/); "Users shouldn't implicitly trust your AI system in all circumstances." — [Explainability + Trust](https://pair.withgoogle.com/chapter/explainability-trust/).

**OpenAI** (F·V)
- Rate tools "low, medium, or high—based on factors like read-only vs. write access, reversibility, required account permissions, and financial impact"; escalate on "Exceeding failure thresholds" and "High-risk actions: Actions that are sensitive, irreversible, or have high stakes should trigger human oversight until confidence in the agent's reliability grows." — [Practical guide, undated PDF](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf).
- "Set `needs_approval` to `True` to always require approval or provide an async function that decides per call."; "Callable approval rules fail closed when the SDK cannot safely inspect the arguments." — [Agents SDK n.d.](https://openai.github.io/openai-agents-python/human_in_the_loop/).

### Inferences
- GitHub separates duties (the requester cannot approve); Linear and Notion keep the delegator responsible. These answer "who is accountable" differently.
- Linear's 2025 changelog describes agents being assigned; current docs describe delegation, so the model evolved.

### Gaps
- Material- or Gemini-specific agent UX guidance and Fluent agent guidance: could not verify. Queries not run (budget): `Google Gemini Agent "asks for confirmation" before critical actions…`; `Microsoft Learn Copilot Studio autonomous agents guidance human oversight…`. Copilot Studio pages were fetched directly.
- PAIR Guidebook edition and OpenAI guide date: not shown in fetched content.
- Copilot Workspace successors: third-party claims only (S).

## 5. Where do these guidance sources disagree?

### Takeaway
Disagreement centres on approval frequency, agent identity and permissions, how visible an agent should be, and where agent UI lives.

### Cited Findings
- Approval frequency: Anthropic argues against mandatory approval of every action, yet calls its own classifier "arguably a regression" against careful manual approval (auto mode post). GitHub makes human review and merge non-optional. Notion offers both "Always ask" and "Skip all approvals". OpenAI treats oversight as temporary.
- Identity and permissions: Linear's agent can "never be mistaken for a person"; Notion Agent "acts as you" in Slack. Notion Agent inherits user permissions; Custom Agents use "the agent's own access"; Copilot Studio says "Data is provided to an agent based on the access level of the current user." (responsible AI page); Google says team agents "need distinct identities and clear authorization models" (Secure AI Agents).
- Visibility: Microsoft wants status "clearly visible at all times" and an agent that "largely operates in the background".
- Where UI lives: Linear says inhabit the platform natively; A2UI renders native components and criticises iframes; MCP Apps and ChatGPT standardise sandboxed iframes in chat; Google Research generates whole pages.

### Inferences
- Disagreements track reversibility: where work lands in a reviewable buffer (branch, draft, page history) vendors relax per-action approval; where actions leave the system (email, payments) every source requires confirmation.

### Gaps
- No source compares these policies on outcomes; Anthropic's first-party data is the only quantitative evidence.

### Closing deliverables

#### (i) Generative-UI approaches
| Approach | Who composes | Who renders | Safety model | Status / date | Source |
|---|---|---|---|---|---|
| Vercel AI SDK UI (tier 1) | Developer builds components; model picks a tool | App's React client | Only developer components; tool data as props | Recommended; RSC `streamUI` variant "experimental"; n.d. | [docs](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces) F |
| AG-UI | Not a UI spec; carries events, state, interrupts | Host app | Typed events; interrupt and resume | 1.0, 2026-09-30 | [blog](https://www.copilotkit.ai/blog/ag-ui-1.0) F |
| A2UI (tier 2) | Agent emits JSON from client catalog | Client renderer, native widgets | Data not code; catalog allowlist; validation | 1.0 stable, 2026-11-11 | [blog](https://developers.googleblog.com/a2ui-10-build-delightful-fast-reliable-agentic-experiences/) F |
| MCP Apps (incl. MCP-UI SDKs) | Server developer pre-declares HTML; model calls tool | Host, sandboxed iframe | Sandbox; reviewable templates; loggable JSON-RPC; consent | Official extension, 2026-01-26 | [blog](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) F |
| OpenAI Apps SDK / ChatGPT plugin UI | Developer MCP server plus UI resource | ChatGPT isolated iframe | CSP allowlists; review; untrusted-input rule | MCP Apps compatible, 2026-02-22 | [changelog](https://developers.openai.com/plugins/changelog) F |
| Artifacts / canvas | Model writes document or code | Vendor side panel | Not stated in fetched pages | 2024-08-27 (S); 2024-10-03 (S); 2025-03-18 (F) | [Claude](https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them) F |
| Fully generated UI (tier 3) | Model writes whole page | Vendor surface | Post-processors fix common issues; isolation not described | Gemini experiments, 2025-11-18 | [Google](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/) F |

#### (ii) Consolidated agent-UX rules (sources as cited in sections 1, 3 and 4)
1. Agent identifies itself as an agent — Linear; Microsoft Copilot Studio; GitHub (commits authored by Copilot). Counter-example: Notion Agent in Slack.
2. A named human stays accountable — Linear (delegate, not assignee); GitHub (human merges); Google (controlling human users).
3. Acknowledge immediately — Linear (webhook 5 s, first activity 10 s).
4. Keep state visible and reasoning inspectable — Linear; Microsoft; Anthropic; Google; GitHub session logs.
5. Confirm irreversible or high-stakes actions — Google; Microsoft Copilot Studio; OpenAI; Anthropic; Notion; Chrome.
6. Tier approvals by risk, reads free — OpenAI; Notion; Anthropic.
7. Stop immediately on request — Linear; Chrome; Anthropic; GitHub; HAX (efficient dismissal).
8. Make changes reversible and say what cannot be undone — Notion; HAX (efficient correction).
9. Least privilege, explicit grants — Notion; Microsoft; Google; GitHub; Anthropic.
10. Ask rather than guess — Linear (elicitation, select); Anthropic; HAX.
11. Bound retries and enforce limits in the runtime — Anthropic; OpenAI; Microsoft.
12. Separate requester from approver — GitHub.
13. Log every run, attributable and auditable — GitHub; Notion; Microsoft; Google.
14. Work through the platform's existing objects — Linear; GitHub (branch, draft pull request).
15. Calibrate trust; logs do not replace review — PAIR; Microsoft; GitHub.
16. Treat tool, page and UI content as untrusted — Google; GitHub; OpenAI; MCP Apps.
17. Start simple, widen autonomy gradually — Anthropic; OpenAI.
18. Hand control back cleanly on failure — PAIR; OpenAI; Linear (error activity).
