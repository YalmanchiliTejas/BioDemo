#!/usr/bin/env bash
# Laptop demo: the API and the app run on this machine, and multi-agent investigations run locally through the
# RLM harness (lead + sub-agents). No DigitalOcean, signing keys or OIDC setup.
#
#   backend/scripts/run_laptop_demo.sh        # then open http://127.0.0.1:5180/sign-in
#
# Only MODEL settings are read from backend/.env.local. Database and Supabase settings are deliberately not loaded,
# and are unset if your shell exported them, so the demo can never write to production data. Demo data lives in
# backend/.cache/laptop-demo.db (delete it to start fresh).
set -euo pipefail
BACKEND="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND"

MODEL_KEYS="MODAL_PROXY_TOKEN BIODEMO_MODAL_PROXY_TOKEN BIODEMO_MODAL_BASE_URL BIODEMO_PRIME_MODEL LIFESCI_LLM_PROVIDER LIFESCI_LLM_MODEL ANTHROPIC_API_KEY OPENAI_API_KEY"
if [[ -f .env.local ]]; then
  # Parse (never source) the file and export only the model keys that the shell does not already set.
  eval "$(python3 - "$MODEL_KEYS" <<'PY'
import os, shlex, sys
wanted = set(sys.argv[1].split())
for line in open('.env.local', encoding='utf-8'):
    key, sep, value = line.strip().partition('=')
    if sep and key in wanted and not os.environ.get(key):
        print(f"export {key}={shlex.quote(value.strip().strip(chr(34)).strip(chr(39)))}")
PY
)"
fi
unset DATABASE_URL LIFESCI_MIGRATION_DATABASE_URL SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_DB_URL SUPABASE_ANON_KEY CMO_DATABASE_URL
mkdir -p .cache
export LIFESCI_DATABASE_URL="sqlite:///$BACKEND/.cache/laptop-demo.db"
export INVESTIGATION_EXECUTOR=local INVESTIGATIONS_ENABLED_TENANTS='*'
export PRIME_AGENT_BUNDLE_ROOT="${PRIME_AGENT_BUNDLE_ROOT:-$HOME/Desktop/prime-agent-bio}"
[[ -f "$PRIME_AGENT_BUNDLE_ROOT/packages/coding-agent/dist/index.js" ]] || {
  echo "Prime SDK not built at $PRIME_AGENT_BUNDLE_ROOT (run 'npm run build' there or set PRIME_AGENT_BUNDLE_ROOT)" >&2; exit 1; }
[[ -n "${MODAL_PROXY_TOKEN:-}${BIODEMO_MODAL_PROXY_TOKEN:-}${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}" ]] || \
  echo "Note: no model credential found; the assistant and investigations will report the model as unavailable." >&2

../.venv/bin/python -m src.lifesci serve --port 8100 --seed-demo &
API=$!
(cd ../frontend && npm run dev:local) &
WEB=$!
trap 'kill $API $WEB 2>/dev/null || true' EXIT INT TERM
echo "Starting… open http://127.0.0.1:5180/sign-in and use a local test account from src/lifesci/devaccounts.py (admin, QA, MSAT, operator)."
wait
