# Agent code workbook

## 1. Run a workspace turn and follow the evidence

From the repository root, paste this into your terminal. Pytest stops inside the test and shows a `(Pdb)` prompt. The fixture uses a synthetic case and scripted model responses.

```sh
cd backend
.venv/bin/python -m pytest -q --trace tests/lifesci/test_tool_loop.py::test_reads_then_answers_with_steps_artifacts_and_grounding
```

Set aside **2–3 hours** for the full workbook, including the experiments and code reading. Spend roughly 20 minutes on this trace, 25 on revisions and access, 20 on budgets, 25 on memory and cancellation, 30 on Prime, and 30 on the final exercise. These are estimates for learning time. The tests themselves run much faster.

For each exercise, write down your prediction before running it. Afterwards, record the value you observed, the line that explains it, and one change that would produce a different result. If a result surprises you, rerun with one variable changed before opening the answer. Keep the same terminal in `backend/` throughout. Scratch tests use a temporary directory and the repository's synthetic fixtures.

A **conversation** holds the exchange over time. A **turn** is the work for one user message. It can contain several model requests, tool calls, and saved results. In this fixture you control what the model requests and says. Your job is to see how the application handles those requests and what it actually saves.

The first test gives its turn unlimited elapsed time so you can read the code while paused. In a regular run, the five-minute exploration budget includes elapsed time between model steps. If it expires after a read, the host adds a “Budget reached” instruction after the tool result and asks for a final answer with tools off. [Workbook test](../tests/lifesci/test_tool_loop.py#L50) · [Time budget check](../src/lifesci/process_engineering/tool_loop.py#L343).

### A. Catch the model's tool request

Enter these lines at `(Pdb)`. `continue` runs to the next breakpoint. `p` prints a value in that frame.

```text
break src/lifesci/process_engineering/tool_loop.py:411
break src/lifesci/process_engineering/workspace.py:249
break tests/lifesci/test_tool_loop.py:56
continue
p name
p args
p name in names
```

Expect `workspace_read`, arguments for `DEV-77` at revision 2, and `True`. The scripted model supplied the name and arguments. The host supplied `names`, the set of tools exposed for this turn. [Tool dispatcher](../src/lifesci/process_engineering/tool_loop.py#L407).

**Read the arguments as a contract.** `kind='case'` selects the record type. `record_id='DEV-77'` identifies the case. `revision=2` says which saved version the caller expects. The fixture opens the case at revision 1 and adds a timeline event, which saves revision 2. A revision belongs to a particular record. It advances when that record is updated. The `True` says the tool name is available in this turn. Whether this caller can read this case is decided in the tool's read path. [Fixture setup](../tests/lifesci/test_tool_loop.py#L14).

### B. Step into the source read

```text
continue
where
p (thread['site_id'], record_id, revision, rec.revision)
p ref
```

Expect `('NF1', 'DEV-77', 2, 2)` and a reference to that case. In the stack from `where`, find `_run_tool`, the operator's `run`, and `read`. You're now just past the authorization check. [Workspace read](../src/lifesci/process_engineering/workspace.py#L243) · [Conversation operator](../src/lifesci/process_engineering/conversation.py#L1046).

### C. Compare what the model saw with what you can reopen

```text
continue
p fake.calls[0]['messages'][0]['role']
p [m['role'] for m in fake.calls[1]['messages']]
p fake.calls[1]['messages'][-1]['role']
p '25 %' in fake.calls[1]['messages'][-1]['content']
p [(s['title'], s['status']) for s in turn['steps']]
p turn['grounding']['status']
p p.engineering_conversations.artifact(ctx, turn['conversation_id'], turn['artifacts'][0]['kind'], turn['artifacts'][0]['id'])['source_refs']
continue
```

Expect `system`, `tool`, `True`, one completed read, and `no_claims`. The saved artifact points back to case revision 2. The final `continue` lets pytest finish.

Draw the message sequence you observed. Label the `system` instructions, the `user` message with the question and workspace context, the `assistant` tool request, and the `tool` response. Mark the point where the tool result becomes a saved artifact. Find the actor who can ask for a read and the code that can actually perform one. Then follow how the entry point got to this loop by looking for the call to `self.tool_loop.run` and the earlier direct-answer branch. [Turn entry](../src/lifesci/process_engineering/conversation.py#L607).

**Try explaining it.** If the reply said the foaming *caused* the drop, would this fixture establish that claim?

<details>
<summary>Check your answer</summary>

The record contains the foaming event and the dissolved oxygen reading. Establishing a cause takes evidence about the relationship between them. `no_claims` means this turn supplied no structured quote claims and the number check found no unsupported values. Follow `_finish` to see what the loop sends to the grounding check. [Finish the turn](../src/lifesci/process_engineering/tool_loop.py#L453) · [Grounding checks](../src/lifesci/process_engineering/grounding.py#L84).

</details>

## 2. Change the requested revision, then change the site

Use this exercise to distinguish a mismatch about **which version** to read from a denial of **who can read** it. The test below drives the same workspace turn as exercise 1.

### A. Establish the baseline in a scratch test

Run this from `backend/`. Keep the printed directory so you can open the test in your editor.

```sh
AGENT_WORKBOOK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-workbook.XXXXXX")
printf '%s\n' "$AGENT_WORKBOOK_DIR"
cat > "$AGENT_WORKBOOK_DIR/test_record_read.py" <<'PY'
import json

from src.lifesci.devseed import TENANT
from tests.lifesci.test_tool_loop import call, env, revision, run


def test_read_contract(env):
    platform, ctx = env
    target = 'DEV-77'
    requested = 2
    with platform.store.transaction('workbook') as tx:
        tx.put(TENANT, 'case', 'OTHER-SITE', {
            'case_id': 'OTHER-SITE', 'site_id': 'NF2', 'timeline': [],
        }, expected_revision=None, action='fixture')

    turn, provider = run(platform, ctx, [
        {'tool_calls': [call('workspace_read', kind='case', record_id=target, revision=requested)]},
        'Finished inspecting the result.',
    ])
    reply = json.loads(provider.calls[1]['messages'][-1]['content'])
    print('exposed:', 'workspace_read' in provider.calls[0]['tools'])
    print('requested:', target, requested, 'current DEV-77:', revision(platform))
    print('step:', turn['steps'][0]['status'], 'artifacts:', len(turn['artifacts']))
    print('model response fields:', sorted(reply))
    if turn['artifacts']:
        artifact = turn['artifacts'][0]
        saved = platform.engineering_conversations.artifact(
            ctx, turn['conversation_id'], artifact['kind'], artifact['id'],
        )
        print('version read:', saved['record']['revision'])
        print('version note:', saved.get('revision_note'))
        print('source refs:', saved['source_refs'])
    else:
        print('tool error:', reply['error'])
PY
.venv/bin/python -m pytest -q -s -c pytest.ini "$AGENT_WORKBOOK_DIR/test_record_read.py"
```

### B. Make one change per run

1. In the scratch file, change `requested` from `2` to `1`. Predict the step status, the revision saved in `source_refs`, and what the tool will tell the model. Rerun the last shell command.
2. Keep `requested = 1` and change `target` to `'OTHER-SITE'`. Predict whether the tool is still exposed, whether a saved result exists, and what the model receives. Rerun. This case exists at revision 1 at `NF2`, while the conversation covers `NF1`.
3. Replace two of your prints with assertions for either run. Break one assertion on purpose and rerun so you can recognize the failure message. Correct the assertion and rerun again.

<details>
<summary>Check your observations</summary>

The first variation succeeds with a `revision_note` and records revision 2, the version actually read. Compare the model response fields with the saved result. The model gets the note and the record. The saved result also retains `source_refs`. In the second variation, the tool stays exposed and the matching revision does nothing to widen access. The step is `blocked`, the model sees a tool error, and there is no saved artifact. Find the site check in `_authorize` and the version comparison in `read`. Which one runs first, and why? [Site and identity checks](../src/lifesci/process_engineering/workspace.py#L143) · [Read behavior](../src/lifesci/process_engineering/workspace.py#L243) · [Model-facing result](../src/lifesci/process_engineering/tool_loop.py#L153).

</details>

## 3. See what happens when the model asks for too much

Stay in `backend/`. This test sets a one-tool allowance and scripts two searches in a single response. Predict how many tools run, how many tool replies go back, and whether the model still gets to answer.

```sh
.venv/bin/python -m pytest -q --trace tests/lifesci/test_tool_loop.py::test_one_model_response_cannot_execute_more_tools_than_the_turn_allows
```

### A. Catch the second call at the budget check

```text
break src/lifesci/process_engineering/tool_loop.py:380
break tests/lifesci/test_tool_loop.py:91
continue
p len(steps)
p len(calls)
p call['arguments']
```

Expect one recorded step, two proposed calls, and the second search for `pressure`. The line you're on sends a tool error back for that call. [Batch budget check](../src/lifesci/process_engineering/tool_loop.py#L378).

### B. See how the model finishes the turn

```text
continue
p len(turn['artifacts'])
p fake.calls[-1]['tool_choice']
p [m['content'] for m in fake.calls[-1]['messages'] if m['role'] == 'tool'][-1]
p turn['reply']
continue
```

<details>
<summary>Check your prediction</summary>

One search ran and saved one artifact. The model received two tool replies, including the budget error for the second search. The last model request used `tool_choice='none'`, so it could answer from the work it had. The host owns this limit and checks it inside the batch. [Test assertions](../tests/lifesci/test_tool_loop.py#L91).

</details>

**Try a different failure.** Run the bad-arguments test. Break on its first assertion, then compare the error the model receives with the two saved step statuses.

```sh
.venv/bin/python -m pytest -q --trace tests/lifesci/test_tool_loop.py::test_a_bad_call_is_a_tool_error_the_model_corrects_not_a_lost_round
```

```text
break tests/lifesci/test_tool_loop.py:71
continue
p fake.calls[1]['messages'][-1]['content']
p [s['status'] for s in turn['steps']]
continue
```

Expect an error about `colour` followed by step statuses `blocked` and `completed`. The scripted model corrects its input on the next attempt. Compare that with the budget case, where the model needs to answer with the work it has. [Bad-call fixture](../tests/lifesci/test_tool_loop.py#L65).

### C. Change the budget instead of the model's request

Use the same scratch directory. Both scripted searches stay fixed while you vary the host allowance.

```sh
cat > "$AGENT_WORKBOOK_DIR/test_budget.py" <<'PY'
from src.lifesci.process_engineering import tool_loop
from tests.lifesci.test_tool_loop import call, env, run


def test_budget_experiment(env, monkeypatch):
    platform, ctx = env
    limit = 1
    monkeypatch.setattr(tool_loop, 'MAX_TOOL_CALLS', limit)
    requests = [call('workspace_search', kinds=['case'], query=q) for q in ('foaming', 'pressure')]
    turn, provider = run(platform, ctx, [{'tool_calls': requests}, 'Finished inspecting the records.'])
    final_call = provider.calls[-1]
    results = [message for message in final_call['messages'] if message['role'] == 'tool']
    print('artifacts:', len(turn['artifacts']))
    print('tool replies:', len(results), 'last tool choice:', final_call['tool_choice'])
    print('errors:', [item['content'] for item in results if 'did not run' in item['content']])
    assert len(results) == len(requests)
PY
.venv/bin/python -m pytest -q -s -c pytest.ini "$AGENT_WORKBOOK_DIR/test_budget.py"
```

Change `limit` to `2`, then to `3`, and rerun for each change. Write down when you expect `tool_choice` to change from `'none'` to `'auto'`. Find the two checks in `ToolLoop.run` that explain the result. Then follow `ask` into the gateway. A **tool call** requests an operation and gets its own result. A **model step** can propose several such calls. The gateway can retry a provider request within one model step. Keep these counts separate when you investigate costs or latency. [Tool loop](../src/lifesci/process_engineering/tool_loop.py#L322) · [Gateway](../src/lifesci/gateway/gateway.py#L201).

<details>
<summary>Check your budget table</summary>

| Allowance | Executed searches | Tool replies | Final tool choice |
| --- | --- | --- | --- |
| 1 | 1 | 2, including the refused call | `none` |
| 2 | 2 | 2 | `none` |
| 3 | 2 | 2 | `auto` |

An allowance of 2 lets both searches run and leaves zero calls for further exploration. An allowance of 3 leaves room, so the provider can propose another tool even though the scripted reply ends the turn. This is why the test compares the request sent to the provider with the number of artifacts actually saved.

</details>

## 4. Find what survives a turn and what happens when you stop it

### A. See what goes into a follow-up

```sh
.venv/bin/python -m pytest -q --trace tests/lifesci/test_tool_loop.py::test_only_recent_turns_are_loaded_older_ones_are_an_index
```

```text
break tests/lifesci/test_tool_loop.py:188
continue
p context.count('detail')
p 'Answer 3' in context
p 'Question 0' in context
p 'earlier_turns_index' in context
continue
```

The fixture creates four long exchanges. Inspect `_history` and write down what it puts in the recent turns and what it puts in the older index. Then compare that with `open_result`, which can reopen a saved artifact by ID. Both use data that lives beyond a model request. A tool transcript is the model's working view. The saved artifact is the record you inspect with access checks. [History assembly](../src/lifesci/process_engineering/tool_loop.py#L217) · [Reopening an earlier result](../tests/lifesci/test_tool_loop.py#L194).

### B. Watch an existing memory note go stale

```sh
.venv/bin/python -m pytest -q --trace tests/lifesci/test_agent_memory.py::test_a_note_goes_stale_when_its_source_record_changes
```

```text
break tests/lifesci/test_agent_memory.py:93
continue
p p.agent_memory.notes(ctx)[0]['status']
next
next
p (note['status'], note['sources'], note['stale_because'])
continue
```

Which object changed in the `next` calls? Which object still points to the earlier revision? Find `_check` in the memory service. Write down whether reading a stale note and persisting its stale status happen at the same point in this test. [Memory fixture](../tests/lifesci/test_agent_memory.py#L90) · [Memory source check](../src/lifesci/agent_memory.py#L195).

### C. Observe cancellation after a tool has computed its result

```sh
env ASSISTANT_LOOP=planner .venv/bin/python -m pytest -q --trace tests/lifesci/test_stop_observation_regression.py::test_stop_during_workspace_tool_does_not_publish_new_artifacts
```

```text
break tests/lifesci/test_stop_observation_regression.py:88
continue
p (entered.is_set(), release.is_set())
p stopped['turns'][-1]['status']
p final['turns'][-1]['artifacts']
p platform.store.read().list(TENANT, 'assistant_workspace_result')
continue
```

Pause after the worker returns. The fixture gives the waiting worker a ten-second timeout, so use the breakpoint shown above when inspecting this test. Draw the order of operations from `pending_search` through `stop`, `release`, and the attempted save. Find `_active_turn` inside the tool's save transaction. The test drives the planner and the shared workspace operator. The native tool loop uses that same operator to save workspace results. [Stop fixture](../tests/lifesci/test_stop_observation_regression.py#L63) · [Commit check](../src/lifesci/process_engineering/conversation.py#L1000) · [Operator transaction](../src/lifesci/process_engineering/conversation.py#L1046).

<details>
<summary>Check your state diagram</summary>

Recent exchanges go into the context in bounded form. Older exchanges get an index and can be retrieved as needed. The note's source reference stays pinned to the revision it was based on. A read detects the change and returns `stale`. The test then runs consolidation and checks that the stale status is stored. In the stop case, the tool computed a search result, the person stopped the turn, and the worker was released. The guard refused to publish the finished work, so both the API view and the store have no new artifact. A turn status is an authority check for publication as well as a progress label.

</details>

## 5. Watch Prime finish after a specialist hands back work

Stay in `backend/`. The Python harness prepares the investigation and launches the Node host that runs Prime's session interface. The **evidence bridge** is a local HTTP service that its tools call to read scoped records and submit findings. This test scripts the SDK's responses and runs the actual host and bridge. It needs Node and local socket access. If your shell blocks the bridge's local socket, [step D](#d-compare-with-a-report-submitted-during-the-wait) runs a lifecycle test with an in-process stub.

```sh
.venv/bin/python -m pytest -q --trace tests/test_sdk_handoff.py::test_real_host_waits_for_child_then_resumes_and_submits
```

### A. Stop before Python starts Node

```text
break src/prime_runtime/harness.py:244
break tests/test_sdk_handoff.py:78
continue
p request['response_mode']
p request['session_file']
p request['prompt']
```

Expect `investigation`, `None` for a new session, and the task objective in the prompt. You're about to launch the Node host. [Harness request](../src/prime_runtime/harness.py#L238).

### B. Run the host and read its events

```text
until 245
p process.returncode
p [json.loads(line)['type'] for line in process.stdout.splitlines() if line.startswith('{')]
p bridge.result['report_status']
```

`until 245` lets Node finish and stops on the next line in this Python frame. Find `awaiting_rlm_quiescence`, `lead_resumed_for_submission`, and `investigation_report_persisted` in that order. The host waits for specialist work, checks for a report, and resumes the lead when there is still work to submit. [Investigation lifecycle](../src/prime_runtime/investigation_lifecycle.mjs#L85).

### C. Check what the harness actually returned

```text
continue
p json.loads((tmp_path/'host-runtime/sessions/handoff-test/host-handoff.json').read_text())
p result['report_status']
continue
```

Expect two prompts, `childDone=True`, and `complete_for_available_evidence`. Find the fixture statements that save the subreport and submit the lead report. [SDK fixture](../tests/test_sdk_handoff.py#L48).

### D. Compare with a report submitted during the wait

Predict the prompt count if a parent turn already submitted during the wait. Run this smaller test and read its last assertion.

```sh
node --test --test-name-pattern='native parent follow-up submits report' tests/test_investigation_lifecycle.mjs
```

<details>
<summary>Check your answer</summary>

The host sent one prompt. The SDK follow-up submitted the report during the wait, and the status check afterwards found it. This says when the host can stop. The coverage test answers a different question by showing how a final report with missing units is returned for more work and how an explicit partial report can be saved with coverage still incomplete. [Follow-up test](../tests/test_investigation_lifecycle.mjs#L35) · [Coverage test](../tests/test_investigation_review.py#L52).

</details>

### E. Inspect what the bridge accepts as a report

This test runs the real report checks over synthetic evidence. It calls the bridge directly and can run without the local socket used in step A.

```sh
.venv/bin/python -m pytest -q --trace tests/test_investigation_review.py::test_screening_and_one_source_citations_cannot_masquerade_as_completion
```

```text
break tests/test_investigation_review.py:56
break tests/test_investigation_review.py:59
break tests/test_investigation_review.py:63
continue
p len(prepared['screening']['coverage_units'])
p len(report['coverage'])
p check['missing_unit_ids']
continue
p (result['status'], bridge.result is None)
continue
p (report['report_type'], bridge.result['report_status'])
p (result['source_verification_status'], result['scientific_validation_status'])
continue
```

At the first stop, match a missing ID to a prepared coverage unit. At the second, find the `needs_more_work` response. At the third, check which field the fixture changed and which coverage gaps stayed. Follow the branches in `submit_report` and explain which transition the Node host can see on its next status check. Then run the sister test for a child submission. Find why the same report payload saves a checkpoint for a child but occupies the final slot when submitted by the lead. [Report dispatcher](../src/prime_runtime/bridge.py#L531) · [Child and lead test](../tests/test_investigation_review.py#L39).

```sh
.venv/bin/python -m pytest -q tests/test_investigation_review.py::test_child_submission_cannot_occupy_final_slot_and_checkpoint_survives
```

## 6. Write a regression for evidence that changes between turns

You own a bug report that says, “The assistant repeated an old result after the underlying case was updated.” Before writing a fix, distinguish two actions. A person can reopen a derived result whose lineage points to revision 2. They can also ask for a fresh read of the case after the source advances to revision 3. Predict which one can be used and what each operation should return. Refer to your revision experiment and the memory note you saw go stale.

Start with this test in your scratch directory. Add assertions at the end that capture the three outcomes you expect. Keep the basic setup and fixture script fixed so the revision change is the variable under test.

```sh
cat > "$AGENT_WORKBOOK_DIR/test_changed_evidence.py" <<'PY'
from tests.lifesci.test_tool_loop import call, env, revision, run


def test_old_result_and_fresh_read_after_case_update(env):
    platform, ctx = env
    conv = platform.engineering_conversations
    old_revision = revision(platform)
    read = {'tool_calls': [call('workspace_read', kind='case', record_id='DEV-77', revision=old_revision)]}
    original, _ = run(platform, ctx, [read, 'I inspected the case.'])
    old_ref = original['artifacts'][0]

    def open_original():
        return conv.artifact(ctx, original['conversation_id'], old_ref['kind'], old_ref['id'])

    assert open_original()['record']['revision'] == old_revision
    platform.cases.add_timeline_event(ctx, 'DEV-77', '2026-11-02T10:00:00Z', 'Probe inspected in workbook fixture.')
    # 1. Confirm that the underlying case has advanced one revision.
    # 2. Try to reopen the old result. Assert the behavior you see and why.
    # 3. Use run() again to make a fresh read in a new conversation. Keep the
    #    old revision in the tool request. Check the resulting artifact's source.
PY
.venv/bin/python -m pytest -q -s -c pytest.ini "$AGENT_WORKBOOK_DIR/test_changed_evidence.py"
```

The starter exercises only the original read and the update. A passing result at this point tells you those steps ran. Add the three checks, make one of them deliberately wrong, and run until you can explain its failure from the code. Restore your assertion and run again.

<details>
<summary>Compare your regression with a reference solution</summary>

Add `import pytest` at the top. Append these assertions inside the test.

```python
assert revision(platform) == old_revision + 1
with pytest.raises(ValueError, match=r'source is no longer current: case:DEV-77@2'):
    open_original()
fresh, provider = run(platform, ctx, [read, 'I reread the current record.'])
new_ref = fresh['artifacts'][0]
saved = conv.artifact(ctx, fresh['conversation_id'], new_ref['kind'], new_ref['id'])
assert fresh['steps'][0]['status'] == 'completed'
assert saved['record']['revision'] == old_revision + 1
assert saved['source_refs'][0]['revision'] == old_revision + 1
assert 'current revision 3' in saved['revision_note']
assert 'Probe inspected in workbook fixture.' in provider.calls[1]['messages'][-1]['content']
```

The old derived result has fixed lineage and reopening it revalidates that lineage. The fresh read has an expected revision in its request, checks the current authorized case, and saves the revision it actually found. Follow the recursive source validation on artifact access and the current record lookup in the fresh read. The test isolates those two operations by using a fresh conversation for the second read. A report about a same-conversation follow-up would need a separate reproduction through that path. [Reopening artifacts](../src/lifesci/process_engineering/conversation.py#L269) · [Source validation](../src/lifesci/identity.py#L276) · [Fresh record read](../src/lifesci/process_engineering/workspace.py#L243).

</details>

### Write the review you would send with a fix

Write five sentences for a teammate. State the observable symptom, the two operations you tested, the layer that enforces the relevant rule, a change you would consider if the person cannot recover, and the evidence you would collect to show the change helps. Compare a small change that makes the current revision and next step clearer with a larger change that automatically reruns the work. Which can save the person effort, and under what conditions should they inspect or approve the change? Name the exact test and assertion you would keep. Use all four product pillars to weigh the trade-off. [Engineering decision rules](../../Main_Culture_andETHOS.md#engineering-decision-rules).

For one more check on your understanding of versioned authority, run the action test below and trace how a revision change invalidates an old approval attempt. Compare the proposal revision, the approved content hash, and what the test writer records. Explain who can approve and what allows dispatch to happen. [Action test](../tests/lifesci/test_core.py#L306) · [Action service](../src/lifesci/actions.py#L61) · [Domain glossary](../../GLOSSARY.md).

```sh
.venv/bin/python -m pytest -q tests/lifesci/test_core.py::test_LS059_LS086_exact_version_approval_and_dispatch
```

### Explain it from a different starting point

Close the answer panels. Pick a symptom you did not start with, such as a tool advertised but refused, an answer delayed by budget, or an accepted Prime report with incomplete coverage. In a fresh terminal, find the relevant test by searching the repository, then run it and show the value and code branch that explain the symptom. Name one change to the fixture that would exercise the opposite branch. If you can predict and verify that change, you have a way to reason about a case the workbook did not spell out.

## How the pieces fit

Open the [system and agent diagrams in draw.io](../../docs/architecture/sievance-current-architecture.drawio). Use **02 · Workspace turn** for the debugger exercises and **03 · Prime investigation** for the specialist handoff. **04 · Assistant memory** follows the same `DEV-77` revision change from a saved note through staleness and later recall. The [memory guide](../../docs/architecture/assistant-memory.md#how-a-note-changes-over-time) links each step to code.

### Workspace assistant

```text
send_message → enqueue → engineering_turn → run_turn
  → tool loop → gateway → proposed call → tool owner → saved result
  → tool result in messages → gateway → reply and grounding diagnostics
```

- **Entry and routing.** The API queues the saved turn. The worker rebuilds the caller's identity and acquires the turn lease. The service tries demo and direct answers first. Remaining work goes to the native loop or the planner. The exercise sets `ASSISTANT_LOOP=tools`. [API entry](../src/lifesci/process_engineering/api.py#L121) · [Turn entry](../src/lifesci/process_engineering/conversation.py#L607) · [Loop switch](../src/lifesci/process_engineering/tool_loop.py#L41).
- **Context and model.** `_setup` assembles authorized sources, recent history, the memory index, and available tools. The prompt gives instructions and names a task route. The gateway selects the model and records its attempts. [Context](../src/lifesci/process_engineering/tool_loop.py#L241) · [Prompt](../src/lifesci/process_engineering/assistant_prompt.py) · [Gateway](../src/lifesci/gateway/gateway.py#L201).
- **State and authority.** The turn stores steps, artifact references, and the reply. The mission owns standing work and corrections. Operators check the active turn before recording results. Reopened artifacts are checked against current access and evidence. Drafts follow a separate approval and execution path. [Turn guard](../src/lifesci/process_engineering/conversation.py#L1000) · [Artifact read](../src/lifesci/process_engineering/conversation.py#L269) · [Action service](../src/lifesci/actions.py#L61).

### Prime investigation

```text
rollout → Python harness → Node host → Prime SDK session
  → scoped evidence bridge → specialist checkpoints → lead report
  → verification → workflow and blackboard
```

- **Host and evidence.** The harness starts or resumes an SDK session. The bridge enforces evidence scope, historical cutoff, and tool admission. To follow a record read, start at the skill's Python client and go through the bridge's dispatcher. [Rollout API](../benchmark/application/api.py#L575) · [Node host](../src/prime_runtime/sdk_runner.mjs#L70) · [Skill client](../prime_skills/manufacturing_os/src/manufacturing_os/__init__.py) · [Evidence tools](../src/prime_runtime/bridge.py#L449).
- **Progress and completion.** Specialist checkpoints preserve work. The lead's report goes through coverage and evidence checks before it is accepted. For a run under review, inspect report status, source verification, and scientific validation separately. SDK session files preserve conversation state, and the host and tool logs explain the run's outcome. [Report submission](../src/prime_runtime/bridge.py#L531) · [Verification](../src/workflows/report_verification.py#L28) · [Host logs](../src/prime_runtime/harness.py#L279).
- **Starting work from the workspace.** The assistant can propose an investigation. A person starts it through the investigation service, which hands the job to the configured executor. The local and cloud workers both call the Prime harness. [Proposal](../src/lifesci/process_engineering/conversation.py#L1157) · [Start](../src/lifesci/investigations.py#L376) · [Local worker](../src/lifesci/local_executor.py#L187) · [Cloud worker](../src/cloud_backend/agent.py#L17).

## Decide where a fix belongs

| What you observe | Where to look first |
| --- | --- |
| The assistant skips part of the question | Compare what reached the model with what the answer covered. Check capability selection for a missing tool. Inspect the prompt and evaluate answer quality if the model had relevant evidence and skipped it. |
| The assistant calls a tool with bad inputs or runs out of budget | Read the tool replies. Find the parser or tool schema for an input error and the host loop for a budget decision. |
| Work is saved after a stop | Follow the active-turn check to the transaction that wrote the record. Reproduce the stop while a tool call is pending. |
| Prime spends another turn after a report exists | Compare the host event order with when the bridge accepted the report. Read the lifecycle's status checks and waits. |
| A report is incomplete | Read the coverage issues and trace them to the report validator and versioned records. |

Use the four product pillars to judge a change. Check the effort to get started, to verify the evidence, to act on the result, and to adopt the change. These exercises establish host behavior with fixtures. Use reviewed live scenarios to evaluate model judgment. [Product pillars](../../Main_Culture_andETHOS.md#the-four-pillars).

The current Python and Prime runtimes apply the Standard Agent Spec's separation of prompts, tools, lifecycle, and thread state. Portable packaging requires TypeScript definitions and a compatible runtime. [Standard Agent Spec v0.2.0](https://standardagentspec.org/) · [Packaging requirements](https://standardagentspec.org/0.2.0/distribution/packaging/).
