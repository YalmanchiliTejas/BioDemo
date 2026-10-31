#!/usr/bin/env bash
# Build the Lambda image, push it to ECR and deploy the CloudFormation (SAM) stack.
#
#   cp deploy/aws/production.env.example deploy/aws/production.env   # fill in; git-ignored
#   deploy/aws/deploy.sh
#
# Needs: AWS CLI v2 signed in to the target account (aws sts get-caller-identity),
# Docker with buildx. Run from anywhere; paths are resolved from this file.
# In CI (.github/workflows/deploy-api.yml) the same variables come from the
# environment instead of production.env, and BUILD_CACHE enables layer caching.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$HERE/../.." && pwd)"
ENV_FILE="${BIODEMO_DEPLOY_ENV:-$HERE/production.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
elif [[ -z "${CI:-}" ]]; then
  echo "Missing $ENV_FILE (copy production.env.example and fill it in)" >&2; exit 1
fi

: "${AWS_REGION:?set AWS_REGION}" "${DATABASE_URL:?}" "${SUPABASE_URL:?}" "${SUPABASE_SERVICE_ROLE_KEY:?}"
: "${DEPLOYMENT_TENANT:?}" "${CORS_ORIGINS:?}"
STACK="${STACK_NAME:-biodemo-api}"
FUNCTION="${FUNCTION_NAME:-biodemo-api}"
REPO="${ECR_REPOSITORY:-biodemo-api}"
export AWS_REGION AWS_DEFAULT_REGION="$AWS_REGION"
# Zero means omit the reservation, not disable the function. Small accounts may
# have no reservable capacity above AWS's required unreserved minimum.
export RESERVED_CONCURRENCY="${RESERVED_CONCURRENCY:-0}"

IFS=',' read -ra ORIGINS <<< "$CORS_ORIGINS"
for origin in "${ORIGINS[@]}"; do
  [[ "$origin" =~ ^https://[^/]+$ ]] || { echo "CORS_ORIGINS entries must look like https://app.example.com (got '$origin')" >&2; exit 1; }
done

if [[ -n "${API_DOMAIN:-}" && -z "${CERTIFICATE_ARN:-}" ]]; then
  echo "Note: API_DOMAIN is set but CERTIFICATE_ARN is empty; deploying without $API_DOMAIN (run deploy/aws/request-certificate.sh)."
fi

case "$DATABASE_URL" in
  postgresql://lifesci_app*|postgres://lifesci_app*) ;;
  *) echo "DATABASE_URL must connect as lifesci_app (the runtime role), not postgres" >&2; exit 1 ;;
esac

# A failed update rollback cannot accept a new change set. Report it before building.
STACK_STATE="$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)"
if [[ "$STACK_STATE" == "UPDATE_ROLLBACK_FAILED" ]]; then
  echo "Stack $STACK is UPDATE_ROLLBACK_FAILED. Fix the deployment-role permissions, then continue rollback before retrying." >&2
  echo "aws cloudformation continue-update-rollback --stack-name $STACK --region $AWS_REGION" >&2
  exit 1
fi

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Start Docker first" >&2; exit 1; }
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com"
echo "Deploying stack $STACK to account $ACCOUNT in $AWS_REGION"

aws ecr describe-repositories --repository-names "$REPO" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$REPO" --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability IMMUTABLE >/dev/null
# Keep the last 10 images; older ones only cost storage.
aws ecr put-lifecycle-policy --repository-name "$REPO" --lifecycle-policy-text \
  '{"rules":[{"rulePriority":1,"description":"keep 10","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10},"action":{"type":"expire"}}]}' >/dev/null
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null

TAG="$(git -C "$BACKEND" rev-parse --short HEAD 2>/dev/null || echo build)-$(date -u +%Y%m%d%H%M%S)"
IMAGE="$REGISTRY/$REPO:$TAG"
# --provenance=false: Lambda does not accept image indexes that carry attestations.
CACHE_ARGS=()
[[ "${BUILD_CACHE:-}" == "gha" ]] && CACHE_ARGS=(--cache-from type=gha,scope=biodemo-api --cache-to type=gha,mode=max,scope=biodemo-api)
docker buildx build --platform linux/arm64 --provenance=false ${CACHE_ARGS[@]+"${CACHE_ARGS[@]}"} -f "$BACKEND/deploy/aws/Dockerfile" \
  -t "$IMAGE" --push "$BACKEND"

export IMAGE FUNCTION
PARAMS="$(mktemp)"; trap 'rm -f "$PARAMS"' EXIT; chmod 600 "$PARAMS"
python3 - "$PARAMS" <<'PY'
import json, os, sys
names = {"ImageUri": "IMAGE", "FunctionName": "FUNCTION", "DatabaseUrl": "DATABASE_URL", "SupabaseUrl": "SUPABASE_URL",
         "SupabaseServiceRoleKey": "SUPABASE_SERVICE_ROLE_KEY", "DeploymentTenant": "DEPLOYMENT_TENANT",
         "CorsOrigins": "CORS_ORIGINS", "StorageBucket": "CMO_STORAGE_BUCKET", "ModalBaseUrl": "MODAL_BASE_URL",
         "ModalProxyToken": "MODAL_PROXY_TOKEN", "LlmModel": "LIFESCI_LLM_MODEL",
         "AllowUnqualifiedRoutes": "LIFESCI_ALLOW_UNQUALIFIED_ROUTES", "SupabaseJwtSecret": "SUPABASE_JWT_SECRET",
         "RuntimeSchedule": "RUNTIME_SCHEDULE", "MemorySize": "MEMORY_SIZE", "ApiDomain": "API_DOMAIN",
         "CertificateArn": "CERTIFICATE_ARN", "MultiTenant": "LIFESCI_MULTI_TENANT",
         "ReservedConcurrency": "RESERVED_CONCURRENCY"}
params = {k: os.environ[v] for k, v in names.items() if os.environ.get(v)}
json.dump({"Parameters": params}, open(sys.argv[1], "w"))  # the form `deploy --parameter-overrides file://` accepts
PY
# A stack whose first creation failed holds nothing and cannot be updated; clear it.
STATE="$(aws cloudformation describe-stacks --stack-name "$STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)"
case "$STATE" in
  ROLLBACK_COMPLETE|ROLLBACK_FAILED)
    echo "Stack $STACK never finished creating ($STATE); deleting it before deploying again"
    aws cloudformation delete-stack --stack-name "$STACK"
    aws cloudformation wait stack-delete-complete --stack-name "$STACK" ;;
esac

if ! aws cloudformation deploy --stack-name "$STACK" --template-file "$HERE/template.yaml" \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset \
  --parameter-overrides "file://$PARAMS"; then
  echo "Deployment failed. Recent resource failures:" >&2
  aws cloudformation describe-stack-events --stack-name "$STACK" \
    --query 'StackEvents[?ResourceStatus==`UPDATE_FAILED` || ResourceStatus==`CREATE_FAILED` || ResourceStatus==`UPDATE_ROLLBACK_FAILED`].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
    --output table >&2 || true
  exit 1
fi

output() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
URL="$(output ApiUrl)"
TARGET="$(output DnsTarget)"
if [[ -n "$TARGET" && "$TARGET" != "None" ]]; then
  echo "DNS: add a CNAME record  ${API_DOMAIN%%.*}  ->  $TARGET  at your domain registrar (once)."
  [[ -n "${GITHUB_STEP_SUMMARY:-}" ]] && echo "DNS: CNAME \`$API_DOMAIN\` → \`$TARGET\`" >> "$GITHUB_STEP_SUMMARY"
fi
if [[ -n "$TARGET" && "$TARGET" != "None" ]]; then
  if ! python3 - "$API_DOMAIN" <<'PYDNS'
import socket, sys
try:
    socket.getaddrinfo(sys.argv[1], 443)
except OSError:
    raise SystemExit(1)
PYDNS
  then
    echo "API_DOMAIN does not resolve yet. Configure its CNAME before pointing the frontend at it."
    echo "Temporary API URL: $(output FunctionUrl)"
  fi
fi
echo "API URL: ${URL%/}"
[[ -n "${GITHUB_STEP_SUMMARY:-}" ]] && echo "API URL: \`${URL%/}\` (image \`$TAG\`)" >> "$GITHUB_STEP_SUMMARY"
# A healthy deployment answers, and refuses an anonymous caller.
DIRECT="$(output FunctionUrl)"
STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${DIRECT%/}/v1/me" || true)"
echo "GET /v1/me without sign-in -> HTTP $STATUS (expected 401)"
echo "Next: set NEXT_PUBLIC_LIFESCI_API_URL=${URL%/} in Vercel and redeploy the frontend."
