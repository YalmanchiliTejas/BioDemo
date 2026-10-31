'use client';

import { WorkspacePageHeader } from './WorkspacePageHeader';

export function SettingsFrame({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <div className="workspace-page"><WorkspacePageHeader title={title} description={description} />{children}</div>;
}
