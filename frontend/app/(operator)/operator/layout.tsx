import { SessionGate } from '@/components/shell/SessionGate';
import { OperatorFrame } from '@/components/shell/OperatorFrame';

export default function OperatorLayout({ children }: { children: React.ReactNode }) {
  return <SessionGate><OperatorFrame>{children}</OperatorFrame></SessionGate>;
}
