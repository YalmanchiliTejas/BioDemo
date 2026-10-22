# Secure backend and autonomous agents: DigitalOcean pilot

Run commands from the backend project root (`cd backend` from the repository
root), unless a command explicitly enters another directory. The checkout on
the Droplet remains `/srv/biodemo/app`; its backend is `/srv/biodemo/app/backend`.

Status: implementation and local verification, **not deployed, SOC 2 examined,
or approved for PHI**. This is a separate backend entry point. The existing
demonstration API and frontend have not been migrated to it.

The user selected DigitalOcean credits and the SFO3 region. The baseline uses one customer per
Droplet, a LUKS-encrypted attached volume, PostgreSQL, private versioned Spaces
objects, Caddy TLS, and a fresh Docker container for each Prime investigation.
Terraform creates the VPC, Droplet, volume, restricted firewall and memory
alert. It deliberately contains no application credentials or model keys.

The dispatcher keeps working after the browser or developer laptop closes.
It reconciles PostgreSQL jobs every five seconds, admits two investigations,
and discovers existing containers after its own restart. Each job has an
absolute deadline and unique fencing token. Cancellation makes subsequent
completion ineligible and removes its container on the next reconciliation.
Agent failures require an explicit new submission; they are not silently
retried. Session checkpoints currently live only for the life of the job
container. Host-reboot recovery does not resume a lost model session.

## Security boundaries

| Area | Implemented boundary |
| --- | --- |
| Identity | RS256 signatures, trusted HTTPS issuer/JWKS, audience, expiry and required subject; no identity from caller scope headers |
| Authorization | Signed `tenant_id` matches the deployment; signed `projects` maps each authorized project to viewer, operator or auditor |
| Audit | Job transitions and audit inserts commit together; reads, denied requests and artifact authorization are recorded without prompts or document text |
| Database | Separate non-owner API/dispatcher logins; no runtime audit update/delete/truncate or DDL rights; TLS with certificate verification |
| Data | SHA-256 plaintext input digest, immutable version references, AES-256-GCM application encryption and per-object HKDF keys |
| Execution | One container per attempt, non-root, read-only root, ephemeral work directory, no host mounts, no Docker socket, no DB/Spaces credentials |
| Resources | 2 CPUs, 2 GiB memory, 128 processes, 1 GiB temporary filesystem, bounded input/output sizes, wall-time and tool-call limits |
| Network | Separate internal network per attempt, external DNS forwarding disabled; only a shared CONNECT proxy can reach the exact approved Spaces/model hosts; private/link-local destinations denied |
| Results | Encrypted output is validated and pinned to its object version before success; report always requires human review |
| Availability | Durable jobs and container reconciliation; encrypted off-host database dump job and six-hour systemd timer supplied |

The API and dispatcher are trusted application services. The dispatcher and
backup service hold the Docker socket, which grants host administrator power.
Agent containers share the host kernel: this pilot is not VM-grade isolation
for mutually untrusted customers. Use separate stacks per customer. A host
administrator can still change database history; append-only SQL permissions
are not immutable external audit storage. Backup copies need separate access
administration and a documented retention/immutability policy.

## Provisioning and bootstrapping

1. Choose the DigitalOcean team, region, SSH key and administrator CIDRs.
   Copy `deploy/cloud/terraform.tfvars.example` to `terraform.tfvars`, fill in
   actual values, and set `DIGITALOCEAN_TOKEN` through your credential manager.
   Run `terraform init`, `terraform plan -out=pilot.tfplan`, review the resources
   and then `terraform apply pilot.tfplan` from `deploy/cloud`. Keep state in
   access-controlled encrypted storage. No apply was run during implementation.
2. Initialize the **new empty attached volume** with LUKS using your host/key
   management procedure, then mount it at `/srv/biodemo`. Formatting an existing
   device destroys its data: identify the Terraform `data_device` output and
   confirm it is the newly created empty volume first. Keep recovery keys in an
   independent vault. The cloud-init Docker unit refuses to start unless this
   mount exists. Configure the mount before starting Docker.
3. Put the checkout at `/srv/biodemo/app`, keeping secrets, Docker state, database
   files, Caddy certificates and backup staging on the encrypted volume. Create
   `/srv/biodemo/backup-staging` with mode 0700. Start Docker after mounting.
   LUKS currently requires an operator to unlock it after a host reboot. Before
   unattended reboot recovery is required, integrate a separately controlled
   key broker and test failure/recovery; do not store the unlock key next to
   the encrypted volume.
4. Create two **private** Spaces buckets for artifacts and backups. Disable CDN
   and public access. Enable artifact versioning through the Spaces API
   (`put_bucket_versioning`, `VersioningConfiguration={"Status":"Enabled"}`)
   and verify it with an upload/read/delete test on synthetic data. Give the
   application a bucket-restricted object credential; use a separate backup
   credential and administrator. No Spaces provisioning credentials are baked
   into Terraform. The API refuses unversioned upload responses.
5. Build the control image from the backend project root:

   ```sh
   docker build --target control -f deploy/cloud/Dockerfile -t REGISTRY/control:pilot .
   ```

   Build/publish a Linux Prime SDK runtime image with its built SDK and Linux
   dependencies under `/opt/prime-agent`. The agent image reuses it:

   ```sh
   docker build --target agent -f deploy/cloud/Dockerfile \
     --build-context prime_runtime=docker-image://REGISTRY/prime-runtime@sha256:APPROVED_DIGEST \
     -t REGISTRY/agent:pilot .
   ```

   The adjacent development runtime is not copied with developer credentials
   or macOS `node_modules`. Pin deployment images to approved registry digests,
   scan them, and pre-pull the agent image on the Droplet. Set the agent model
   explicitly. Node must be 22.21+; `NODE_USE_ENV_PROXY=1` is set for its model
   traffic. An actual approved model/Prime image smoke run remains a deployment
   acceptance test, not a claimed result of local queue tests.
6. Copy `deploy/cloud/.env.example` to `.env`, set public configuration, and
   replace the example hosts in `squid.conf` with the **exact** regional bucket
   hostname and approved model hostname. The proxy rejects other destinations.
   Configure DNS for `API_DOMAIN`; Caddy issues its TLS certificate. Do not
   publish the legacy demo service, Docker API, PostgreSQL or proxy ports.
7. From the encrypted checkout, run
   `sudo python3 scripts/bootstrap_cloud_secrets.py`. It prompts without echo,
   creates unique passwords, a master encryption key, distinct bucket keys and
   a 90-day DB TLS certificate. It refuses to overwrite existing secrets.
   Back up the master key independently: losing it loses artifact and database
   backup access. Apply your approved key rotation schedule before PHI use;
   automatic key rewrapping/rotation is not implemented.
8. Start only the database, then initialize runtime passwords as root:

   ```sh
   cd /srv/biodemo/app/backend/deploy/cloud
   docker compose up -d db
   docker compose exec -T db psql -v ON_ERROR_STOP=1 -U migration_admin -d investigations < secrets/initialize_passwords.sql
   ```

   Remove the temporary password-initialization SQL after successful execution.
   On an existing database, run schema migrations as the migration identity
   explicitly; do not grant DDL to API or dispatcher identities.
9. Configure the identity provider to issue API tokens with server-controlled
   `tenant_id` and `projects` claims. Users must not be able to edit those
   attributes. Enforce MFA and short sessions in the identity provider. Example
   authorization claims (these values are not a valid token):

   ```json
   {"sub":"employee-id","tenant_id":"pilot-customer","projects":{"project-1":"operator"}}
   ```

   Viewer reads job/results; operator uploads/submits/cancels/reads; auditor
   reads job/results/audit. There is no self-service global administrator role.
   Membership changes take effect on newly issued tokens; bound token TTL and
   session revocation are identity-provider responsibilities.
10. Run `docker compose config --quiet`, `docker compose up -d`, then verify
    unauthenticated requests fail and run a synthetic package end to end. Check
    that agents cannot access the DB, metadata IPs or arbitrary Internet hosts.
    Verify an allowed model request succeeds through the proxy. Kill/restart
    the dispatcher during a run and test cancellation.
11. Run `docker compose --profile operations run --rm backup`. Install the
    supplied systemd service/timer under `/etc/systemd/system`, then enable
    `biodemo-backup.timer`. Monitor timer failures and off-host backup age.
    The dump is streamed directly into GCM encryption before writing to staging.
    It is a consistent logical snapshot, not continuous WAL/PITR protection.

## API integration contract

Use an `Authorization: Bearer ...` token for every operation. Neither
`X-Tenant-ID` nor `X-Roles` grants access. The only unauthenticated route is
`GET /healthz`, which reports process liveness without data.

1. `PUT /v1/projects/{project}/inputs/{plaintext_sha256}` with ZIP bytes, max
   64 MiB. The server verifies the digest, encrypts the bytes and returns
   `sha256` and `version_id`.
2. `POST /v1/projects/{project}/jobs` with an `Idempotency-Key` header and JSON:

   ```json
   {"sha256":"64 lowercase hex digits","version_id":"returned version",
    "objective":"Investigate the authorized evidence",
    "as_of":"2026-10-22T00:00:00Z","timeout_seconds":900,"max_tool_calls":72}
   ```

   The same key and input returns the same job. Reusing it with different input
   returns 409. Deadline includes admission-to-launch overhead. Queued time
   before admission does not count against the investigation deadline.
3. Poll `GET /v1/projects/{project}/jobs/{id}`. States are `queued`, `running`,
   `succeeded`, `failed`, `cancelled`. Browser disconnection does not cancel work.
4. `POST .../jobs/{id}/cancel` stops eligibility immediately and execution on
   reconciliation. A container already in progress may take several seconds
   to terminate; cancellation does not undo external model requests already sent.
5. `GET .../jobs/{id}/result` returns a decrypted JSON report only for a
   successful, authorized job. Results require review; they do not authorize
   manufacturing changes, batch release or external-system writes.
6. `GET /v1/projects/{project}/audit` returns the latest 200 metadata events to
   project auditors. This is a bounded inspection endpoint, not a complete
   compliance evidence export. Preserve full history through scheduled backups
   and your independently administered evidence pipeline.

## Restore exercise

In an isolated restoration environment, retrieve a selected encrypted dump and
recover its exact object path. Its binary format is `BIO1`, 12-byte GCM nonce,
ciphertext, 16-byte authentication tag. Derive the key with `object_key(master,
object_path)` and authenticate the object path as additional data. Small test
backups can be recovered using `unseal`; production restore should stream GCM
decryption and verify the authentication tag **before** invoking `pg_restore`.
Restore into a fresh isolated PostgreSQL database, create runtime roles/grants,
and verify job counts, audit history, project access and a result's pinned Spaces
version. Record backup timestamp, actual data loss window, restore duration and
reviewer. Do not restore over the running production database as a drill.

Define RPO/RTO with the customer. A six-hour successful backup schedule alone
does not prove a six-hour RPO: alerting, retention, encryption-key recovery and
restoration must also work. Droplet snapshots do not replace attached-volume
or application-consistent database backups.

## Verification and remaining controls

Run `CLOUD_TEST_DATABASE_URL=... .venv/bin/python -m pytest -q tests/cloud`
against a **disposable** PostgreSQL database: tests truncate their cloud tables.
Without that variable, database tests skip. The tests exercise real PostgreSQL
transactions and privileges; Docker/Spaces reconciliation tests use fakes.
Terraform validate and Compose config validate are read-only checks. A control
image build does not establish an agent/provider deployment works.

| Control/evidence | Current status | Before regulated production |
| --- | --- | --- |
| SOC 2 system boundary and control owners | Technical boundary described here | Appoint owners, select examination scope/auditor and collect operation evidence |
| HIPAA risk analysis and privacy/security policies | Not conducted | Document risk assessment, policies, workforce training and incident/breach procedures |
| Business associate/vendor chain | Not executed | DigitalOcean BAA and eligible-service confirmation; model endpoint/identity/backup vendor review and applicable BAAs |
| Identity lifecycle | Verified-token integration implemented | Configure MFA, joiner/mover/leaver process, emergency access and periodic access reviews |
| Data minimization and retention | Encrypted scoped objects implemented | Approve retention/deletion, legal holds and incident evidence preservation; versioned objects need version-aware deletion |
| Auditing | Transactional metadata audit and runtime append-only privileges | Independently administered retention/immutability, review alerts and complete evidence exports |
| Backups and continuity | Encrypted dump job/timer supplied | Restore drill, monitored schedule, agreed RPO/RTO, off-host key recovery and host-reboot unlock procedure |
| Vulnerability/change management | Image digest enforcement and infrastructure code | Scan/patch images and host; change review, deployment evidence, penetration test and incident exercise |
| Resource/cost control | Task/tool/time/concurrency limits | Vendor-enforced total token/spend quotas; native child costs are not fully enforced by the Python harness |
| Tenant isolation | Per-customer deployment and scoped API | Test the chosen isolation boundary under realistic workloads; VM isolation if threat model requires it |

SOC 2 is an independent examination of controls, not a property conferred by
this code. HIPAA requires administrative, physical and technical safeguards in
the applicable regulated relationship. Relevant primary sources:
[AICPA SOC services](https://www.aicpa-cima.com/resources/landing/system-and-organization-controls-soc-suite-of-services?visualEditor=convert),
[HHS Security Rule](https://www.hhs.gov/hipaa/for-professionals/security/index.html),
[HHS cloud guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html),
[DigitalOcean HIPAA scope and BAA](https://www.digitalocean.com/trust/hipaa-at-do),
[DigitalOcean Spaces limitations](https://docs.digitalocean.com/products/spaces/details/limits/),
[Node proxy support](https://nodejs.org/learn/http/enterprise-network-configuration).
