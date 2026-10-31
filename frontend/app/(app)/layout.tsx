import { SessionGate } from '@/components/shell/SessionGate';
import { AppShell } from '@/components/shell/AppShell';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <SessionGate><AppShell>{children}</AppShell></SessionGate>;
}
