import { OperatorFrame } from '@/components/shell/OperatorFrame';

export default function OperatorLayout({ children }: { children: React.ReactNode }) {
  return <OperatorFrame>{children}</OperatorFrame>;
}
