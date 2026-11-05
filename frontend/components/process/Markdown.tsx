import { Fragment, type ReactNode } from 'react';

/** Renders the small Markdown subset model replies use (paragraphs, headings, lists, bold, italic, code)
 *  as React elements. No HTML is ever injected, so reply text cannot add markup or scripts.
 *  ponytail: no tables/links; add a real renderer if replies start relying on them. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let last = 0, match: RegExpExecArray | null, key = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith('**') || token.startsWith('__')) out.push(<strong key={key++} className="font-semibold">{token.slice(2, -2)}</strong>);
    else if (token.startsWith('`')) out.push(<code key={key++} className="rounded bg-surface-secondary px-1 py-0.5 text-[0.92em]">{token.slice(1, -1)}</code>);
    else out.push(<em key={key++}>{token.slice(1, -1)}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block = { kind: 'p' | 'h' | 'ul' | 'ol'; lines: string[] };

function blocks(source: string): Block[] {
  const result: Block[] = [];
  for (const raw of source.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/), numbered = line.match(/^\s*\d+[.)]\s+(.*)$/), heading = line.match(/^#{1,6}\s+(.*)$/);
    const top = result.at(-1);
    if (!line.trim()) { result.push({ kind: 'p', lines: [] }); continue; }
    if (heading) result.push({ kind: 'h', lines: [heading[1]] });
    else if (bullet) top?.kind === 'ul' ? top.lines.push(bullet[1]) : result.push({ kind: 'ul', lines: [bullet[1]] });
    else if (numbered) top?.kind === 'ol' ? top.lines.push(numbered[1]) : result.push({ kind: 'ol', lines: [numbered[1]] });
    else if (top?.kind === 'p' && top.lines.length) top.lines.push(line.trim());
    else result.push({ kind: 'p', lines: [line.trim()] });
  }
  return result.filter(b => b.lines.length);
}

export function Markdown({ text, className = '' }: { text: string; className?: string }) {
  return <div className={`space-y-3 text-sm leading-7 text-text-primary ${className}`}>
    {blocks(text).map((b, i) => b.kind === 'h' ? <p key={i} className="font-semibold">{inline(b.lines[0])}</p>
      : b.kind === 'ul' ? <ul key={i} className="list-disc space-y-1 pl-5">{b.lines.map((l, j) => <li key={j}>{inline(l)}</li>)}</ul>
      : b.kind === 'ol' ? <ol key={i} className="list-decimal space-y-1 pl-5">{b.lines.map((l, j) => <li key={j}>{inline(l)}</li>)}</ol>
      : <p key={i}>{b.lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>)}
  </div>;
}
