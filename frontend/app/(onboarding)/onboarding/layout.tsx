import { OnboardingFrame } from '@/components/shell/OnboardingFrame';

export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  return <OnboardingFrame>{children}</OnboardingFrame>;
}
