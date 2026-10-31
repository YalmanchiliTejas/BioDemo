# Authentication and connection onboarding

The job is to let invited team members enter their authorized workspace, connect an existing source, inspect a sample and start observable collection. The implementation extends the existing Supabase identity and connector service rather than adding a second identity provider or ingestion system.

A simple option was to retain the simulated source gallery with a link to administrator configuration. The implemented option exposes the existing connector contracts in a short interactive flow. It adds configuration controls but avoids a separate provisioning service and migration. Server-managed credentials still require an administrator; this preserves deployment boundaries at the cost of fully self-service credential setup.

The four pillars guide the flow: discover available source families and authorized sites; preview mapping and expose source errors; provide explicit first-sync and recurring collection controls; preserve existing source systems, role assignments and credential storage. Useful rollout measures are time from invitation to successful API identity check, time to the first successful source preview, manual configuration fields required, mapping failures and age of the latest successful collection. No improvement in these measures has yet been measured.

## Configure a deployment

1. Set the frontend values shown in `frontend/.env.example` before building. These are build-time settings for the statically exported app. Use the same Supabase project on the frontend and backend.
2. Configure the API with `LIFESCI_AUTH_MODE=supabase`, `SUPABASE_URL`, `DEPLOYMENT_TENANT` and explicit `LIFESCI_CORS_ORIGINS`. Keep public signup disabled under the existing invitation-only policy. Follow `backend/deploy/aws/README.md` for the deployed stack.
3. Add the site's `/set-password/` URL to Supabase Auth's redirect allowlist. Configure the production Site URL and email delivery. Invites and recovery links use the existing Supabase session handling.
4. Invite each person through Supabase Authentication. Set the invitation redirect to `https://<site>/set-password/`. Create a stored role assignment using the existing backend CLI (for example `python -m src.lifesci grant-role --email <email> --role admin --site <site-id> --tenant <tenant-id> --reason '<reason>'`). Choose the least privileged existing role that meets the person's responsibilities. Signing in does not grant connector permissions.
5. Set `LIFESCI_CONNECTOR_ALLOWED_HOSTS` to approved source hosts. Install read credentials as environment secrets on the API host. Users enter secret *names*, never secret values. For file sources set `LIFESCI_CONNECTOR_FILE_ROOT`, and mount the source folder under it. MQTT/OPC UA need their optional packages and a persistent server; they are not supported by the Lambda deployment.
6. Set `LIFESCI_TENANTS` or `DEPLOYMENT_TENANT` for polling recovery after restart. Persistent API hosts run the existing runtime loop. On Lambda, the existing scheduled runtime invocation must remain enabled; actual polling cadence is bounded by that schedule. A requested one-minute connector interval cannot make a five-minute infrastructure scheduler run more frequently.

## Use the flow

- Open `/sign-in/`. Supabase signs in the person, then `/v1/me` confirms that the API recognizes their workspace permissions. Invitation password creation continues to `/onboarding/start/`; recovery continues to the workspace.
- `/onboarding/start/` and `/sources/` use the same live catalog and saved connections. They do not fall back to synthetic connectors when an API fails. Unconfigured authentication is explicitly identified as development mode.
- Choose a family, site and transport, then save. A new connection starts in manual mode. No write operations are enabled. Optional REST response fields and source-to-canonical field mappings live under advanced settings.
- Preview REST, file or OPC UA sources. This reads a sample without persisting evidence or advancing the ingestion checkpoint. Review mapping errors before proceeding. MQTT starts durable collection on sync. Webhooks supply an API receiver path and use signed source deliveries instead of scheduled pulls.
- Choose an interval and explicitly run the first sync. The frontend enables the schedule only after that request succeeds. Existing checkpoints, deduplication and provenance remain owned by the connector backend.
- Saved connections can be configured, synced manually, paused and resumed. Saving revised settings returns a connection to manual mode for retesting. Pause and schedule changes preserve the previous sync result. Changing a source or mapping clears its previous status. Pausing prevents future collection; it does not cancel a request already in flight.

## Before inviting a real team

Verify an actual invitation and recovery email in the configured project; confirm authorized site access and denial to an unauthorized account; preview an approved source with real read credentials; observe a successful first sync and a later server-scheduled sync; pause and resume it. The implementation's local tests do not establish those live services are ready, and connection preview is not vendor qualification or a compliance claim.
