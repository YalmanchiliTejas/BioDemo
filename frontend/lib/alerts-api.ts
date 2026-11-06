import { processRequest } from '@/lib/process-api';

export type Severity = 'warning' | 'action' | 'critical';
export type InboxItem = { inbox_id: string; signal_id: string; site_id: string | null; severity: Severity; kind?: string; title: string;
  rule: string; subject?: { kind?: string; id?: string } | null; link: string; created_at: string; read_at: string | null;
  updates: { kind: string; at: string; text: string }[] };
export type ChannelKind = 'email' | 'slack' | 'teams';
export type AlertChannel = { channel_id: string; kind: ChannelKind; name: string; config: Record<string, unknown>; enabled: boolean;
  secret_fields: string[]; updated_at: string };
export type AlertRoute = { route_id: string; site_id: string | null; min_severity: Severity; roles: string[]; channels: string[];
  enabled: boolean; default?: boolean };

export const inbox = () => processRequest<{ items: InboxItem[]; unread: number }>('/v1/notifications');
export const markRead = (id: string) => processRequest<InboxItem>(`/v1/notifications/${encodeURIComponent(id)}/read`, {});
export const listChannels = () => processRequest<{ channels: AlertChannel[] }>('/v1/alert-channels');
export const saveChannel = (body: { channel_id?: string; kind: ChannelKind; name: string; config?: Record<string, unknown>;
  secrets?: Record<string, string>; enabled?: boolean }) => processRequest<AlertChannel>('/v1/alert-channels', body);
export const testChannel = (id: string) => processRequest<{ status: string }>(`/v1/alert-channels/${encodeURIComponent(id)}/test`, {});
export const listRoutes = () => processRequest<{ routes: AlertRoute[] }>('/v1/alert-routes');
export const saveRoute = (body: Omit<AlertRoute, 'route_id' | 'default'> & { route_id?: string }) => processRequest<AlertRoute>('/v1/alert-routes', body);

export const SEVERITY_LABEL: Record<Severity, string> = { warning: 'Early warning', action: 'Out of specification', critical: 'Critical' };
