import { ConnectorOnboarding } from '@/components/ConnectorOnboarding';
import { SettingsFrame } from '@/components/shell/SettingsFrame';
export default function SourcesPage() {
  return <SettingsFrame title="Data connections" description="Connect your systems, verify mappings, and manage collection."><div className="setup-shell setup-in-workspace"><ConnectorOnboarding embedded /></div></SettingsFrame>;
}
