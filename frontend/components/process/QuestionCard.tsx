'use client';

import { useState } from 'react';
import { ArrowUp, MessageCircleQuestion } from 'lucide-react';

/** The assistant's open questions, each with its own answer box, sent back as one message.
 *  Unanswered questions are sent as "not known" so the assistant can proceed or say what it still needs. */
export function QuestionCard({ questions, disabled, onAnswer }: { questions: string[]; disabled: boolean; onAnswer: (text: string) => void }) {
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ''));
  const answered = answers.filter(a => a.trim()).length;
  function submit() {
    if (!answered || disabled) return;
    onAnswer(questions.map((q, i) => `${i + 1}. ${q}\n   ${answers[i].trim() || 'Not known yet.'}`).join('\n'));
  }
  return <form className="mt-4 rounded-card border border-brand-teal/30 bg-brand-teal-light/30 p-4" onSubmit={e => { e.preventDefault(); submit(); }}
    aria-label="Questions from the assistant">
    <p className="flex items-center gap-2 text-sm font-medium text-text-primary"><MessageCircleQuestion size={16} className="text-brand-teal" />
      {questions.length === 1 ? 'I need one thing from you' : `I need ${questions.length} things from you`}</p>
    <ol className="mt-3 space-y-3">{questions.map((q, i) => <li key={q}>
      <label htmlFor={`answer-${i}`} className="block text-sm leading-6 text-text-primary">{q}</label>
      <textarea id={`answer-${i}`} rows={1} value={answers[i]} disabled={disabled} placeholder="Your answer (leave blank if unknown)"
        onChange={e => setAnswers(a => a.map((v, j) => j === i ? e.target.value : v))}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
        className="mt-1.5 block w-full resize-y rounded-control border border-border-strong bg-surface px-3 py-2 text-sm outline-none focus:border-brand-teal disabled:opacity-60" />
    </li>)}</ol>
    <div className="mt-3 flex items-center justify-between gap-3">
      <p className="text-[11px] text-text-tertiary">{answered}/{questions.length} answered · blank answers are sent as “not known yet”</p>
      <button type="submit" disabled={!answered || disabled} className="inline-flex items-center gap-1.5 rounded-control bg-brand-teal px-3 py-2 text-xs font-medium text-white hover:bg-brand-teal-dark disabled:opacity-40">
        Send answers<ArrowUp size={14} /></button>
    </div>
  </form>;
}
