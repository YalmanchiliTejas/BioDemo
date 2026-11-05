#!/usr/bin/env bash
# Create the RS256 key the platform API uses to sign service tokens for the investigation executor,
# store it in AWS Secrets Manager, and print the values for the GitHub repository variables.
# The private key never touches disk: it is piped straight into Secrets Manager.
#
#   AWS_REGION=us-west-2 backend/deploy/aws/create-investigation-signing-key.sh
#
# Needs the AWS CLI signed in to the production account (aws sts get-caller-identity) and openssl.
set -euo pipefail
: "${AWS_REGION:?set AWS_REGION (the region the API is deployed in)}"
NAME="${SECRET_NAME:-biodemo/investigation-signing-key}"
KEY_ID="${KEY_ID:-investigation-$(date -u +%Y%m)}"

if aws secretsmanager describe-secret --secret-id "$NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "Secret $NAME already exists; not overwriting. Use a new SECRET_NAME to rotate." >&2
  exit 1
fi
ARN="$(openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 2>/dev/null \
  | aws secretsmanager create-secret --name "$NAME" --region "$AWS_REGION" \
      --description "RS256 key: platform API -> investigation executor service tokens" \
      --secret-string file:///dev/stdin --query ARN --output text)"
cat <<EOF

Created $ARN
Add these as GitHub repository *variables* (Settings → Secrets and variables → Actions → Variables):
INVESTIGATION_SIGNING_KEY_SECRET_ARN=$ARN
INVESTIGATION_SIGNING_KEY_ID=$KEY_ID
EOF
