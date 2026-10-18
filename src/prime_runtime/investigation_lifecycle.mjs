/** A model turn ending is not an investigation ending. Own the SDK fan-in. */
export const FINALIZE_PROMPT = 'The investigation phase has ended. Stop exploration and child spawning. Read work_queue() and saved progress. Use assemble_report() and explicitly import relevant specialist checkpoints; preserve valid saved sections. Repair specific validate_report issues instead of rewriting the report. Include explicit coverage, claim classifications, uncertainties and required deliverables, then submit_report. If required work remains, explicitly submit partial_investigation. Never relabel screening or unresolved work as complete.';
export const RESUME_PROMPT = 'Continue the existing investigation. Your previous lead turn ended, but no validated report has been submitted. Specialist runs and their terminal follow-up messages have now drained. Read context(), work_queue() and saved checkpoints; explicitly import completed subreports, resolve remaining work, validate and submit_report. Do not restart the investigation or duplicate completed evidence searches. If a child failed, preserve its valid findings and explicitly identify the missing work. A progress message or saved draft alone does not complete this task.';

export async function runInvestigation(session, {
  prompt, readStatus, timeoutSeconds, finalizationReserveSeconds = 90,
  getFatalError = () => undefined, emit = () => {},
}) {
  if (typeof session.waitForRlmQuiescence !== 'function') {
    throw Error('SDK lacks waitForRlmQuiescence; update the SDK before running recursive investigations');
  }
  if (!Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0) {
    throw Error('Investigation host requires a positive finite wall-clock deadline');
  }
  const exploration = new AbortController();
  let finalizing = false;
  let expired = false;
  let stopping;
  let rejectDeadline;
  const deadline = new Promise((_, reject) => { rejectDeadline = reject; });
  // Cancellation is best effort; the Python process-group deadline remains
  // authoritative if a provider/kernel cannot be interrupted.
  const stopExploration = () => {
    exploration.abort();
    for (const child of session.getRlmChildSnapshots?.() ?? []) {
      if (['running', 'queued'].includes(child.status)) {
        session.cancelRlmChildRun?.(child.id, 'Final synthesis reserve reached; retain saved checkpoints');
      }
    }
    stopping = Promise.resolve(session.abort());
    stopping.catch(() => {});
  };
  const hardTimer = setTimeout(() => {
    expired = true;
    emit({type:'investigation_deadline', timestamp:new Date().toISOString()});
    rejectDeadline(Error('Investigation host reached its wall-clock deadline; no report completion is inferred'));
    stopExploration();
  }, timeoutSeconds * 1000);
  const reserveTimer = setTimeout(() => {
    finalizing = true;
    emit({type:'finalization_reserve', timestamp:new Date().toISOString()});
    stopExploration();
  }, Math.max(0, timeoutSeconds - finalizationReserveSeconds) * 1000);
  const bounded = operation => Promise.race([operation, deadline]);
  const checkError = () => {
    const error = getFatalError() ?? session.agent?.state?.errorMessage;
    if (error && !finalizing) throw Error(error);
    if (getFatalError()) throw Error(getFatalError());
  };
  const promptTurn = async text => {
    try {
      await bounded(session.prompt(text));
    } catch (error) {
      // Reserve cancellation can reject an in-flight prompt as well as the
      // descendant barrier. It must transfer control to synthesis in both.
      if (!finalizing || expired || getFatalError()) throw error;
    }
  };
  let continuations = 0;
  try {
    await promptTurn(prompt);
    while (true) {
      checkError();
      const submitted = await bounded(readStatus());
      if (submitted.final_report_submitted) {
        emit({type:'investigation_report_persisted', timestamp:new Date().toISOString(),
          report_status:submitted.report_status});
        return submitted;
      }
      // Strong SDK fan-in includes descendants, queued terminal messages,
      // automatic parent turns, and children spawned by those parent turns.
      if (!finalizing) {
        emit({type:'awaiting_rlm_quiescence', timestamp:new Date().toISOString(),
          running_children:(session.getRlmChildSnapshots?.() ?? []).filter(c => ['running','queued'].includes(c.status)).length});
        try {
          await bounded(session.waitForRlmQuiescence(exploration.signal));
        } catch (error) {
          if (!finalizing) throw error;
        }
      }
      if (stopping) await bounded(stopping);
      checkError();
      const status = await bounded(readStatus());
      if (status.final_report_submitted) {
        emit({type:'investigation_report_persisted', timestamp:new Date().toISOString(),
          report_status:status.report_status});
        return status;
      }
      if (finalizing) {
        // Drain cancellation notices before admitting the synthesis prompt;
        // otherwise it can race an SDK-generated parent continuation.
        if (session.waitForHeadlessIdle) await bounded(session.waitForHeadlessIdle());
        await bounded(session.prompt(FINALIZE_PROMPT));
        await bounded(session.waitForHeadlessIdle?.() ?? Promise.resolve());
        checkError();
        const final = await bounded(readStatus());
        if (final.final_report_submitted) {
          emit({type:'investigation_report_persisted', timestamp:new Date().toISOString(),report_status:final.report_status});
          return final;
        }
        throw Error('Final synthesis ended without submitting a validated report; inspect saved checkpoints and report validation issues');
      }
      continuations += 1;
      emit({type:'lead_resumed_for_submission', continuation:continuations,
        timestamp:new Date().toISOString()});
      await promptTurn(RESUME_PROMPT);
    }
  } finally {
    clearTimeout(reserveTimer);
    clearTimeout(hardTimer);
    exploration.abort();
  }
}
