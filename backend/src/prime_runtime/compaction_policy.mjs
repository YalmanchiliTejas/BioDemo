/** Session-local context policy: start summarizing history at a target size. */
export const COMPACTION_RESERVE_TOKENS = 32768;

export function compactionWindow(model, targetTokens) {
  if (targetTokens === undefined || targetTokens === null) return null;
  const target = Number(targetTokens);
  if (!Number.isInteger(target) || target < 32000) {
    throw new Error("compaction_target_tokens must be an integer of at least 32000");
  }
  const native = model?.contextWindow;
  if (!Number.isFinite(native)) return null;
  const contextWindow = target + COMPACTION_RESERVE_TOKENS;
  if (contextWindow >= native) return null;
  return { target_tokens: target, context_window: contextWindow, native_context_window: native };
}
