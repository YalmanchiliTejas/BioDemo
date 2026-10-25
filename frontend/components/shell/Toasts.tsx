'use client';

import { CheckCircle2, Info, AlertTriangle, X } from 'lucide-react';
import { useAppContext } from '@/lib/app-context';

export function Toasts() {
  const { toasts, dismissToast } = useAppContext();
  return (
    <div className="fixed bottom-14 right-4 z-[100] flex flex-col gap-2 w-[340px] max-w-[calc(100vw-2rem)]" aria-live="polite">
      {toasts.map((t) => {
        const Icon = t.tone === 'success' ? CheckCircle2 : t.tone === 'warning' ? AlertTriangle : Info;
        const color = t.tone === 'success' ? 'text-status-success' : t.tone === 'warning' ? 'text-status-warning' : 'text-data-blue';
        return (
          <div key={t.id} className="flex items-start gap-2.5 bg-surface border border-border-hairline rounded-card shadow-lg px-3 py-2.5 text-[13px] text-text-primary">
            <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${color}`} aria-hidden />
            <p className="flex-1">{t.message}</p>
            <button onClick={() => dismissToast(t.id)} className="text-text-tertiary hover:text-text-primary" aria-label="Dismiss"><X className="h-3.5 w-3.5" /></button>
          </div>
        );
      })}
    </div>
  );
}
