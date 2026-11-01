/** Native task answers are distinct from validated investigation packages. */
export function parseTaskResponse(messages) {
  const message = [...messages].reverse().find(m => m.role === 'assistant');
  if (!message || message.errorMessage || message.content?.some(c => c.type === 'toolCall')) throw Error('Agent did not finish with a task answer');
  const text = (message.content ?? []).filter(c => c.type === 'text').map(c => c.text).join('').trim();
  const valid = answer => answer && answer.task_answer && typeof answer.task_answer === 'object' && !Array.isArray(answer.task_answer) &&
    Array.isArray(answer.evidence_ids) && answer.evidence_ids.length && answer.evidence_ids.every(id => typeof id === 'string' && id);
  const candidates=[];
  // One complete structured answer may be surrounded by explanatory prose.
  // No answer-key lookup, prose interpretation, or best-of-candidates selection.
  for (let start=0; start<text.length; start++) {
    if (text[start]!=='{') continue;
    let depth=0, quoted=false, escaped=false;
    for (let end=start; end<text.length; end++) {
      const char=text[end];
      if (quoted) {if (escaped) escaped=false; else if (char==='\\') escaped=true; else if (char==='"') quoted=false; continue;}
      if (char==='"') quoted=true;
      else if (char==='{') depth++;
      else if (char==='}' && --depth===0) {
        try {const answer=JSON.parse(text.slice(start,end+1)); if (valid(answer)) candidates.push(answer);} catch {}
        start=end; break;
      }
    }
  }
  if (candidates.length!==1) throw Error('Expected one unambiguous task_answer with visible evidence_ids');
  return candidates[0];
}
export async function runTaskResponse(session, {prompt, timeoutSeconds}) {
  let timer;
  try {
    await Promise.race([
      (async () => { await session.prompt(prompt); await session.waitForRlmQuiescence(); })(),
      new Promise((_, reject) => {timer=setTimeout(() => {void session.abort(); reject(Error('Task answer deadline reached'));}, timeoutSeconds*1000);}),
    ]);
    return parseTaskResponse(session.messages);
  } finally {clearTimeout(timer);}
}
