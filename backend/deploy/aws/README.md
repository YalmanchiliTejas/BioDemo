# Deploying on AWS Lambda + Vercel + Supabase + Modal

| Piece | Where | What it does |
|---|---|---|
| Frontend | Vercel | Static Next.js export; signs users in with Supabase Auth |
| API | AWS Lambda (container image, function URL) | FastAPI app; background work runs as asynchronous self-invocations |
| Data | Supabase | PostgreSQL (normalized schema, RLS), Storage (original files), Auth |
| Assistant model | Modal | OpenAI-compatible chat completions (`zai-org/GLM-5.3`) |

## How the API behaves on Lambda

- **Background work.** CMO delivery checks and assistant turns are sent to the
  same function as asynchronous invocations, each with a 15-minute limit. On a
  normal server they run in threads; the code path is the same
  (`src/lifesci/tasks.py`).
- **Run progress lives in the database.** A run is saved as `queued` before
  any work starts. Only the first worker to claim it proceeds, so a duplicate
  delivery of the task does nothing. A run still `queued` or `running` after
  16 minutes is reported as interrupted (`CMO_RUN_TIMEOUT_SECONDS`).
- **The schedule replaces the runtime thread.** Every minute it handles
  mission timers, connector polls and queued data flows. It also keeps one
  instance warm.
- **Uploads go to storage directly.** Lambda accepts at most 6 MB per request,
  so the browser uploads each file to a signed Supabase Storage URL. The API
  then downloads it, validates and hashes it exactly like a direct upload,
  stores it under the delivery, and deletes the transport copy.
- **Only `/tmp` is writable.** Parse caches live there and are rebuilt when
  needed. Original files are restored from Storage and re-hashed before use.
- **Unsafe settings stop the function at start-up:** an in-memory or SQLite
  database, missing Storage credentials, schema migration at runtime, or
  development identity headers on a public URL.

Not available on Lambda: document parsing with Docling (it needs GPU-class
models; deterministic and `pypdf` parsing work), sample-ZIP uploads (`/upload`),
MQTT/OPC UA connectors and LiveKit. All of these need long-lived processes.

## One-time setup

1. **Supabase** (already done if you followed `deploy/supabase/README.md`):
   - run `0002` and `0003`;
   - create the private bucket `cmo-evidence`;
   - under Authentication, enable email/password sign-ups with email confirmation for self-service organizations (or disable sign-ups for invitation-only deployments), and turn on asymmetric
     JWT signing keys (ES256);
   - set the Site URL to the Vercel address, and add
     `https://<app>.vercel.app/set-password/` to the redirect URLs.
2. **AWS:** install Docker and the AWS CLI v2, then sign in
   (`aws configure sso` or access keys). Check it with
   `aws sts get-caller-identity`.
3. **Settings:**
   `cp deploy/aws/production.env.example deploy/aws/production.env` and fill
   it in. The file is git-ignored. `DATABASE_URL` must use the `lifesci_app`
   login.

## Deploy the API

```bash
cd backend
deploy/aws/deploy.sh
```

The script builds an arm64 image, pushes it to ECR, deploys the stack, and
prints the API URL. It then checks that an anonymous request is refused with
HTTP 401. Run it again to deploy a new version.

## Deploy from GitHub Actions (recommended)

`.github/workflows/deploy-api.yml` runs on every push to `main` that touches
the backend, and can also be started by hand (Actions → Deploy API → Run
workflow). It runs the tests with exactly the Lambda dependencies, then builds
the image on a native arm64 runner and runs `deploy.sh`. GitHub signs in to
AWS with a short-lived OIDC token, so no AWS keys are stored in GitHub.

One-time setup:

1. **AWS role** (as an administrator, console):
   - Go to CloudFormation → Create stack → With new resources → Upload a
     template file, and upload `deploy/aws/github-oidc.yaml`.
   - Name the stack `biodemo-github-oidc`.
   - Keep the defaults. Set `CreateOidcProvider` to `false` only if IAM →
     Identity providers already lists `token.actions.githubusercontent.com`.
   - Acknowledge that IAM resources will be created, then submit.
   - This creates the role `biodemo-github-deployer` with the
     `biodemo-lambda-deploy` policy. Only jobs in this repository's
     `production` environment can use it.
2. **GitHub settings:** with `production.env` filled in, run
   `deploy/aws/github-settings.sh`. It needs the GitHub CLI
   (`brew install gh && gh auth login`). It creates the `production`
   environment and stores:
   - **secrets:** `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
     `MODAL_PROXY_TOKEN`
   - **variables:** `AWS_REGION`, `AWS_DEPLOY_ROLE_ARN`, `SUPABASE_URL`,
     `DEPLOYMENT_TENANT`, `CORS_ORIGINS`, `MODAL_BASE_URL`, and the model
     settings

   You can also enter these by hand under Settings → Environments →
   production.
3. **Optional:** add required reviewers to the `production` environment, so
   every deploy waits for an approval.

Then push to `main`, or run the workflow by hand. The run summary shows the
API URL.

## Deploy the frontend (Vercel)

1. Import the GitHub repository in Vercel and set **Root Directory** to
   `frontend`. Build command `npm run build`, output directory `dist`.
2. Add these environment variables:
   - `NEXT_PUBLIC_LIFESCI_API_URL` = the API URL printed by `deploy.sh`
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. Deploy. If the Vercel address changed, put it in `CORS_ORIGINS` and run
   `deploy.sh` again.

## Give people access

Invite users from Supabase (Authentication → Users → Invite). Then assign each
one a role, with `LIFESCI_DATABASE_URL` pointing at the production database:

```bash
python -m src.lifesci grant-role --email person@company.com --role msat --site NF1
python -m src.lifesci list-roles
```

An account without a role can sign in but cannot see any data.

## Costs (approximate list prices; check current AWS pricing)

- **Requests:** within the free tier at demo volumes.
- **Parsing a delivery:** about 3 GB × 1–2 minutes, under one cent each.
- **The every-minute schedule:** about 43,000 short invocations a month, well
  within the free tier.
- **ECR:** about $0.10 per GB-month for stored images (the script keeps 10).
- **Not included:** Supabase and Modal billing.

## Known limits

- **Response size:** buffered responses are capped at 6 MB. Very large CSV or
  XLSX exports fail with an error rather than being cut short.
- **Cold starts:** the first request after an idle period takes longer. The
  schedule keeps one instance warm.
- **Service role key:** the backend holds `SUPABASE_SERVICE_ROLE_KEY` for
  Storage. A Storage-only S3 access key would be narrower; that is a follow-up.
- **Not tested against live accounts.** Nothing here has been run against a
  real AWS, Supabase or Modal account.

## Recovering the October 31 startup and account failures

These are independent deployment concerns:

- **`ModuleNotFoundError: benchmark`:** rebuild the Lambda image. Runtime connector contracts now live in `src/lifesci/connector_contracts.py`, and the image build constructs a platform to catch missing startup dependencies. Do not bundle the evaluation corpus to fix a runtime dependency.
- **`EMAXCONNSESSION`:** deploy the connection lifecycle fix. The optional concurrency cap can be enabled once the AWS account has sufficient quota. Each invocation releases its session. Keep the session-pooler URL on port 5432 for this store; its tenant-binding reads depend on session state. Do not increase concurrency beyond database capacity or change only the pooler port. Other applications using the same runtime user also consume pool slots.
- **`ERR_NAME_NOT_RESOLVED`:** publish `api.sievance.com CNAME dox69po0s3xpi.cloudfront.net` at the authoritative DNS provider (the target reported by the current `biodemo-api` stack in `us-east-1`). Verify the current stack output before changing DNS. Until the custom hostname resolves, the stack's `FunctionUrl` is an alternative API base URL; rebuilding the frontend is required when changing a `NEXT_PUBLIC_*` value.
- **Development headers in production:** set all three public frontend values in Vercel: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_LIFESCI_API_URL`. Redeploy/rebuild; these are embedded at build time. Do not put the service-role key in the frontend. Missing auth configuration now fails closed in production.

### Enable signup and organizations

1. Deploy the backend and frontend changes together. The SAM template sets `LIFESCI_MULTI_TENANT=1`; set `MultiTenant=0` explicitly for an invitation-only single-tenant deployment. No new SQL schema is needed: organization and discovery records use the existing versioned store and tenant policies.
2. Enable Supabase email/password registration, require email confirmation, and configure production SMTP. Retain password-strength and abuse/rate limits appropriate to the deployment.
3. Set the Supabase Site URL to `https://www.sievance.com` and allow `https://www.sievance.com/account/` and `https://www.sievance.com/set-password/` as redirect URLs. Add equivalent URLs for any separately supported frontend origin.
4. Include the exact frontend origins (for example `https://www.sievance.com,https://sievance.com`) in `CORS_ORIGINS`. The API allows the organization-selection header.
5. Register a new account, confirm its email, create an organization, finish or skip data-source setup, sign out and sign in again. Then register a second account and grant it access from Organization & access. Verify it cannot select an unrelated organization and that revocation takes effect.
6. Verify anonymous `GET /v1/account` returns 401, a valid account without memberships can list its empty account, and `GET /v1/me` requires an active organization membership. Watch Lambda connection counts during concurrent authenticated requests and background tasks.

Existing role assignments in `DEPLOYMENT_TENANT` remain discoverable. New accounts do not inherit them. See [accounts and organizations](../../../docs/architecture/accounts-and-organizations.md) for the authorization model and current site-scope boundary.

### Deployment role concurrency permissions and failed rollback

If updating `Api` fails with `lambda:PutFunctionConcurrency` denied, and rollback fails with `lambda:DeleteFunctionConcurrency` denied:

1. As an AWS administrator, open IAM → Policies → `biodemo-lambda-deploy` → Edit policy → JSON. Apply the current `deploy/aws/deployer-policy.json` and save a new default version. The Lambda function statement includes `lambda:PutFunctionConcurrency` and `lambda:DeleteFunctionConcurrency`, scoped to `biodemo-api`. The stack statement includes `cloudformation:ContinueUpdateRollback`.
2. In CloudFormation (`us-east-1`), select `biodemo-api` → Stack actions → Continue update rollback. Do not skip the `Api` resource. Wait for `UPDATE_ROLLBACK_COMPLETE`. Alternatively, using an authorized identity:

   ```bash
   aws cloudformation continue-update-rollback --stack-name biodemo-api --region us-east-1
   aws cloudformation describe-stacks --stack-name biodemo-api --region us-east-1 --query 'Stacks[0].StackStatus' --output text
   ```

3. Rerun the deployment workflow. The failed stack must recover before a new update can proceed. There is no need to delete the stack or change the CNAME. The deployment script now checks this state before building and prints resource failure reasons when deployment fails.

The recovery command needs permission on the stack. If the identity running it does not have `cloudformation:ContinueUpdateRollback`, use an administrator or update the scoped deployer policy first.

### Reserved concurrency exceeds account headroom

If `Api` fails with `Specified ReservedConcurrentExecutions ... decreases account's UnreservedConcurrentExecution below its minimum value`, the account cannot currently allocate the requested reservation. The observed account requires at least 10 unreserved executions.

The template and deployment script now default `RESERVED_CONCURRENCY=0`. This **omits** `ReservedConcurrentExecutions` through `AWS::NoValue`; it does not set Lambda concurrency to zero, which would disable invocations. The deploy script explicitly sends the parameter so an earlier value of 5 is replaced. For GitHub Actions, leave the `RESERVED_CONCURRENCY` repository/environment variable unset or set it to `0`. Then deploy the updated code. A stack in `UPDATE_ROLLBACK_COMPLETE` can be updated directly; no further rollback recovery is needed.

Connection cleanup remains enabled. Omitting the cap removes the application-specific concurrency bound: concurrent active requests and other database clients can still exhaust the session pool. Monitor database sessions and throttling under representative load. After obtaining enough Lambda quota, set the reservation to 1–5 with measured database headroom. Do not set the Lambda function's actual reserved concurrency to zero in the AWS console.
