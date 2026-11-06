# Turning on multi-agent investigations: step-by-step setup

## Now: free laptop demo (no cloud setup)

Multi-agent investigations (your RLM harness: a lead agent spawning investigator sub-agents) are a **paid feature**. In production they stay off, and the proposal card says they're part of the paid plan. For demos, run the whole product on your laptop:

```bash
backend/scripts/run_laptop_demo.sh      # then open http://127.0.0.1:5180/sign-in
```

What the script does:
- It runs investigations in-process through the harness at `~/Desktop/prime-agent-bio`, with the same live investigator view as production.
- It reads only model settings from `backend/.env.local` (`MODAL_PROXY_TOKEN`, model names, API keys). It deliberately doesn't load your database or Supabase settings, so a demo can never write to production data.
- Demo data lives in `backend/.cache/laptop-demo.db`.
- Sign in with a local test account (`src/lifesci/devaccounts.py`).
- To demo: upload a sample delivery (`backend/scripts/make_sample_delivery.py`), ask the assistant for a full investigation of a deviation, and press Start.

Defaults keep cost down: 30 tool calls, 10 minutes, one investigation at a time. Model usage goes through your own provider account.

**Switching it on for a paying customer** means doing the server setup below, then adding their organization ID to the API setting `INVESTIGATIONS_ENABLED_TENANTS` (comma-separated). Nobody else sees the feature.

---

## Later: hosted investigations for paying customers

This is the plain-language checklist for switching on investigations in production. The architecture is in [multi-agent-investigations.md](../architecture/multi-agent-investigations.md); the full security runbook for the DigitalOcean stack is [cloud-backend.md](../../backend/docs/security/cloud-backend.md). Nothing here is required for the rest of the product: until you finish, the app says "Investigation execution isn't set up for this workspace yet".

## What you're building, in one picture

```
Your app (Vercel) ──► Your API (AWS Lambda, already live)
                          │  signs a 5-minute token, sends a sealed evidence ZIP
                          ▼
                     DigitalOcean server ("executor")
                       runs Prime in a fresh container per investigation,
                       streams progress back, returns a sealed report
```

You set up three things: (A) the DigitalOcean server, (B) a model key inside it, (C) a signing key and six settings on the AWS side. Then you run one test investigation.

## Before you start: accounts and tools

| You need | Why | How to get it |
| --- | --- | --- |
| DigitalOcean account + **API token** (write scope) | Terraform creates the server with it | DigitalOcean → API → Generate New Token |
| An **SSH key** in DigitalOcean | To log in to the server | DigitalOcean → Settings → Security → Add SSH Key; note its ID (`doctl compute ssh-key list`) |
| A **DigitalOcean Container Registry** | Holds the three images | DigitalOcean → Container Registry → Create (Basic plan is enough) |
| A **subdomain** you control, e.g. `exec.yourdomain.com` | The executor's HTTPS address | Your DNS provider |
| Your **public IP** | Only you can SSH in | `curl -s ifconfig.me` |
| **Model provider key** (e.g. Anthropic) | Prime calls the model | Your provider console |
| AWS CLI signed in to production | Creates the signing key | `aws sts get-caller-identity` should show the production account |
| Tools on your Mac | | `brew install terraform doctl` (Docker you already have) |

**Approval first (step 0).** Evidence and reports will be stored on DigitalOcean (SFO3). The runbook states that stack is **not SOC 2 examined or approved for PHI**. Decide who in your organization approves that data path. Until it's approved, use only the synthetic sample delivery (`backend/scripts/make_sample_delivery.py`).

## A. The DigitalOcean server (≈1–2 hours the first time)

1. **Create the server with Terraform** (~10 min)
   ```bash
   cd backend/deploy/cloud
   cp terraform.tfvars.example terraform.tfvars     # edit: ssh_key_ids, admin_cidrs = ["<your IP>/32"], operations_email
   export DIGITALOCEAN_TOKEN=...                    # paste in your terminal; never commit it
   terraform init
   terraform plan -out=pilot.tfplan                 # read what it will create: VPC, Droplet, volume, firewall
   terraform apply pilot.tfplan
   terraform output                                 # note the Droplet IP and data_device
   ```
   Cost is the Droplet plus a volume, running continuously; check the plan's sizes against DigitalOcean pricing.

2. **Point DNS** (~5 min): create an `A` record `exec.yourdomain.com → <Droplet IP>`.

3. **Encrypt and mount the data volume** (~15 min, on the server: `ssh root@<IP>`). Follow runbook step 2 exactly. The one thing to get right: `luksFormat` **erases** the device you name. Use only the `data_device` from `terraform output` and confirm it's empty with `lsblk` first. Store the passphrase in your password manager; you'll need it after every reboot.

4. **Object storage** (~10 min): DigitalOcean → Spaces → create two **private** buckets in `sfo3` (artifacts, backups), CDN off. Create a Spaces access key limited to each bucket. Turn on versioning for the artifacts bucket (runbook step 4 has the one-line API call).

5. **Build and push the images** (~20–40 min, on your Mac):
   ```bash
   doctl registry login
   cd backend
   deploy/cloud/build-images.sh registry.digitalocean.com/<your-registry>
   ```
   It builds the Prime runtime from `~/Desktop/prime-agent-bio` (override with `PRIME_SOURCE=...`), then the control and agent images, pushes them and prints `CONTROL_IMAGE=` / `AGENT_IMAGE=` lines for the next step.

6. **Configure the server** (~20 min, on the server, in `/srv/biodemo/app/backend/deploy/cloud`):
   - Copy `.env.example` to `.env`. Fill in `API_DOMAIN=exec.yourdomain.com`, the two image lines from step 5, the Spaces region, endpoint and bucket names, and `BIODEMO_PRIME_MODEL`. Then set the four values that connect it to your API:
     ```
     OIDC_ISSUER=<same as INVESTIGATION_ISSUER below, e.g. https://api.yourdomain.com>
     OIDC_JWKS_URL=https://api.yourdomain.com/.well-known/investigation-jwks.json
     OIDC_AUDIENCE=biodemo-executor
     DEPLOYMENT_TENANT=<your production DEPLOYMENT_TENANT>
     ```
   - Edit `squid.conf` so the only allowed hosts are your Spaces bucket host and your model provider's API host.
   - Run `sudo python3 scripts/bootstrap_cloud_secrets.py`. It asks for the Spaces keys and the **model key** (part B) without echoing them, and generates the rest. Back up the master key it prints.
   - Start the database and initialise it (runbook step 8). Then apply the schema and roles, which include the new investigation event table:
     ```bash
     docker compose exec -T db psql -v ON_ERROR_STOP=1 -U migration_admin -d investigations < /srv/biodemo/app/backend/src/cloud_backend/schema.sql
     docker compose exec -T db psql -v ON_ERROR_STOP=1 -U migration_admin -d investigations < /srv/biodemo/app/backend/src/cloud_backend/runtime_roles.sql
     ```
   - `docker compose up -d`, then `curl -s https://exec.yourdomain.com/healthz` should answer, and an unauthenticated job request should be refused.

## B. The model key (part of A.6)

The agent calls the model through the server's proxy using the key you enter at the "Approved model endpoint credential" prompt of `bootstrap_cloud_secrets.py`. Two settings in `.env` tell it how to use that key:
- `BIODEMO_PRIME_MODEL`: written `provider/model`, for example `anthropic/<model id>`.
- `MODEL_SECRET_ENV`: the name of the environment variable your provider's SDK reads the key from, for example `ANTHROPIC_API_KEY`. Use a key dedicated to investigations, with a spending limit set in the provider's console. That's your hard money cap, because v1 only enforces tool, time and token limits.

## C. The AWS side (≈15 min)

1. **Signing key:**
   ```bash
   AWS_REGION=<your API region> backend/deploy/aws/create-investigation-signing-key.sh
   ```
   It creates the key directly in Secrets Manager (it's never written to disk) and prints two variables.

2. **GitHub repository variables** (GitHub → Settings → Secrets and variables → Actions → **Variables**):

   | Variable | Value |
   | --- | --- |
   | `INVESTIGATION_EXECUTOR_URL` | `https://exec.yourdomain.com` |
   | `INVESTIGATION_EXECUTOR_AUDIENCE` | `biodemo-executor` (must equal `OIDC_AUDIENCE`) |
   | `INVESTIGATION_EXECUTOR_TENANT` | your `DEPLOYMENT_TENANT` |
   | `INVESTIGATION_EXECUTOR_PROJECT` | a short name, e.g. `investigations` |
   | `INVESTIGATION_ISSUER` | your API's public URL, e.g. `https://api.yourdomain.com` (must equal `OIDC_ISSUER`) |
   | `INVESTIGATION_SIGNING_KEY_SECRET_ARN` | printed by step C.1 |
   | `INVESTIGATION_SIGNING_KEY_ID` | printed by step C.1 |

3. **Redeploy the API:** GitHub → Actions → Deploy API → Run workflow. Check `https://api.yourdomain.com/.well-known/investigation-jwks.json` returns a key.

## D. First test investigation (≈20 min)

1. In the app: Deliveries → upload `make_sample_delivery.py` output → confirm mappings. Then in the assistant ask "Do a full investigation of DEV-31" and press **Start** on the proposal card.
2. Within a minute you should see investigators appear, with live tools and calls. If nothing appears, check in order: the card says "not configured" (part C variables are missing) → "execution service unreachable" (DNS, TLS or firewall) → the run fails at once (OIDC values don't match, or `docker compose logs api` shows a 401).
3. Record what the design asks for: time to first investigator activity, run duration, whether the report validated, and tokens used.

## What can be done for you

Every step that needs your credentials or creates paid resources is yours to run: the DigitalOcean token, the Terraform apply, the LUKS passphrase, the model key, the AWS key creation and the GitHub variables. With you at the keyboard, Claude Code can run or explain any command above, read error output, and fix configuration in this repository.
