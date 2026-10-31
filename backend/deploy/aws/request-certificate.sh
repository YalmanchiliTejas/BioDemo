#!/usr/bin/env bash
# Request (or find) the TLS certificate for the custom API hostname and print
# the DNS record that proves you own the domain. Run once, locally:
#
#   deploy/aws/request-certificate.sh api.sievance.com
#
# CloudFront only accepts certificates from us-east-1. Once the record is added
# at your registrar, AWS issues the certificate (usually within minutes); put
# its ARN in CERTIFICATE_ARN (production.env and the GitHub variable).
set -euo pipefail
DOMAIN="${1:?usage: request-certificate.sh api.example.com}"
export AWS_DEFAULT_REGION=us-east-1

ARN="$(aws acm list-certificates --certificate-statuses PENDING_VALIDATION ISSUED \
  --query "CertificateSummaryList[?DomainName=='$DOMAIN'].CertificateArn | [0]" --output text)"
if [[ -z "$ARN" || "$ARN" == "None" ]]; then
  ARN="$(aws acm request-certificate --domain-name "$DOMAIN" --validation-method DNS \
    --idempotency-token "$(echo "$DOMAIN" | tr -cd '[:alnum:]' | cut -c1-32)" --query CertificateArn --output text)"
  echo "Requested a certificate for $DOMAIN"
  sleep 5   # the validation record appears a few seconds after the request
fi

read -r STATUS NAME VALUE < <(aws acm describe-certificate --certificate-arn "$ARN" \
  --query "[Certificate.Status, Certificate.DomainValidationOptions[0].ResourceRecord.Name, Certificate.DomainValidationOptions[0].ResourceRecord.Value]" \
  --output text)
echo "CERTIFICATE_ARN=$ARN"
echo "Status: $STATUS"
if [[ "$STATUS" != "ISSUED" ]]; then
  echo
  echo "Add this record at your domain registrar (DNS settings for ${DOMAIN#*.}):"
  echo "  Type:  CNAME"
  echo "  Host:  ${NAME%.${DOMAIN#*.}.}      (some registrars want the full name: ${NAME%.})"
  echo "  Value: ${VALUE%.}"
  echo
  echo "Then run this script again to check; it says ISSUED once AWS has seen the record."
fi
