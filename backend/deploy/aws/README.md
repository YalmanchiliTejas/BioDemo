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
   - under Authentication, turn off public sign-ups and turn on asymmetric
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
