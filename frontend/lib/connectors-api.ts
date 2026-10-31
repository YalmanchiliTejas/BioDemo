import { authHeaders, authMode, redirectToSignIn, SIGNED_OUT_MESSAGE } from './auth';
import { PROCESS_API } from './process-api';
export type Identity = {
    tenant_id: string;
    actor_id: string;
    roles: string[];
    site_ids: string[];
    auth_mode: string;
};
export type Mapping = {
    template_id: string;
    version: string;
    fields: {
        source: string;
        canonical: string;
        [key: string]: unknown;
    }[];
    [key: string]: unknown;
};
export type Connector = {
    connector_id: string;
    family: string;
    transport: string;
    site_id: string;
    owner: string;
    vendor: string;
    version: string;
    options: Record<string, string | number | string[]>;
    enabled: boolean;
    mapping?: Mapping;
    write_operations: string[];
    last_sync?: string;
    last_error?: string;
    revision?: number;
};
export type Catalog = {
    families: {
        system: string;
        record_type: string;
        template: Mapping;
    }[];
    transports: {
        transport: string;
        available: boolean;
    }[];
};
export async function connectorRequest<T>(path: string, body?: unknown): Promise<T> {
    let response: Response;
    try {
        response = await fetch(`${PROCESS_API}/v1${path}`, { method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json', ...await authHeaders() }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(45000) });
    }
    catch {
        throw new Error('Cannot reach the workspace API. Check your connection and try again.');
    }
    if (response.status === 401 && authMode() === 'supabase') {
        redirectToSignIn();
        throw new Error(SIGNED_OUT_MESSAGE);
    }
    const data = await response.json().catch(() => null);
    if (!response.ok)
        throw new Error(response.status === 403 ? 'Your account does not have access to configure connections for this site. Ask your administrator for access.' : typeof data?.detail === 'string' ? data.detail : `The request failed (${response.status}). Check your configuration and try again.`);
    return data as T;
}
// Never send status fields back as configuration; the server remains authoritative.
export function configuration(c: Connector): Connector {
    const { connector_id, family, transport, site_id, owner, vendor, version, options, enabled, mapping, write_operations } = c;
    return { connector_id, family, transport, site_id, owner, vendor, version, options, enabled, mapping, write_operations };
}
