#!/usr/bin/env bash
# Copy deployment settings from production.env into the repository's GitHub
# "production" environment: secrets for credentials, variables for the rest.
# Needs the GitHub CLI signed in with admin rights on the repository
# (brew install gh && gh auth login). Secrets are sent on stdin, never echoed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${BIODEMO_DEPLOY_ENV:-$HERE/production.env}"
REPO="${GITHUB_REPOSITORY:-YalmanchiliTejas/BioDemo}"
ENVIRONMENT=production

command -v gh >/dev/null || { echo "Install the GitHub CLI: brew install gh && gh auth login" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a; source "$ENV_FILE"; set +a
[[ "${CORS_ORIGINS:-}" =~ ^https:// ]] || { echo "Set CORS_ORIGINS in $ENV_FILE to your Vercel address first" >&2; exit 1; }

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
AWS_DEPLOY_ROLE_ARN="${AWS_DEPLOY_ROLE_ARN:-arn:aws:iam::$ACCOUNT:role/biodemo-github-deployer}"

gh api -X PUT "repos/$REPO/environments/$ENVIRONMENT" >/dev/null
for name in DATABASE_URL SUPABASE_SERVICE_ROLE_KEY MODAL_PROXY_TOKEN SUPABASE_JWT_SECRET; do
  if [[ -n "${!name:-}" ]]; then
    printf '%s' "${!name}" | gh secret set "$name" --repo "$REPO" --env "$ENVIRONMENT"
    echo "secret   $name"
  fi
done
for name in AWS_REGION AWS_DEPLOY_ROLE_ARN SUPABASE_URL DEPLOYMENT_TENANT CORS_ORIGINS MODAL_BASE_URL \
            LIFESCI_LLM_MODEL LIFESCI_ALLOW_UNQUALIFIED_ROUTES API_DOMAIN CERTIFICATE_ARN; do
  if [[ -n "${!name:-}" ]]; then
    gh variable set "$name" --repo "$REPO" --env "$ENVIRONMENT" --body "${!name}"
    echo "variable $name"
  fi
done
echo "Done. Actions → Deploy API → Run workflow (or push to main) to deploy."
