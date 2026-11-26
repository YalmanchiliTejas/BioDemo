/** Frozen sensitivity intervention: final provider turn can only submit. */
export function applySubmissionOnlyPolicy(payload, ordinal, maxCalls) {
  if (ordinal !== maxCalls) return;
  const submission = (payload.tools ?? []).filter(tool => tool.function?.name === 'submit_decision');
  if (submission.length !== 1) throw Error('Final-turn submission schema missing or duplicated');
  payload.tools = submission;
  payload.tool_choice = { type: 'function', function: { name: 'submit_decision' } };
}
