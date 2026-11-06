#!/usr/bin/env bash
# Build (and optionally push) the three images the DigitalOcean investigation stack runs.
#
#   deploy/cloud/build-images.sh                         # local build only, for a smoke test
#   deploy/cloud/build-images.sh registry.digitalocean.com/<your-registry>   # build + push
#
# PRIME_SOURCE points at the Prime SDK checkout (default ~/Desktop/prime-agent-bio).
# Prints the image references to paste into deploy/cloud/.env on the Droplet.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "$HERE/../.." && pwd)"
REGISTRY="${1:-}"
PRIME_SOURCE="${PRIME_SOURCE:-$HOME/Desktop/prime-agent-bio}"
PLATFORM="${PLATFORM:-linux/amd64}"   # DigitalOcean Droplets are x86_64
TAG="${TAG:-$(git -C "$BACKEND" rev-parse --short HEAD)}"
[[ -f "$PRIME_SOURCE/packages/coding-agent/package.json" ]] || { echo "PRIME_SOURCE=$PRIME_SOURCE is not a Prime checkout" >&2; exit 1; }

name() { [[ -n "$REGISTRY" ]] && echo "$REGISTRY/$1:$TAG" || echo "biodemo-$1:$TAG"; }
OUT=(--load); [[ -n "$REGISTRY" ]] && OUT=(--push)

echo "1/3 Prime runtime from $PRIME_SOURCE"
docker buildx build --platform "$PLATFORM" -f "$HERE/prime-runtime.Dockerfile" -t "$(name prime-runtime)" "${OUT[@]}" "$PRIME_SOURCE"

echo "2/3 Control image (API + dispatcher)"
docker buildx build --platform "$PLATFORM" --target control -f "$HERE/Dockerfile" -t "$(name control)" "${OUT[@]}" "$BACKEND"

echo "3/3 Agent image"
if [[ -n "$REGISTRY" ]]; then
  DIGEST="$(docker buildx imagetools inspect "$(name prime-runtime)" --format '{{.Manifest.Digest}}')"
  PRIME_REF="docker-image://$REGISTRY/prime-runtime@$DIGEST"
else
  PRIME_REF="docker-image://$(name prime-runtime)"
fi
docker buildx build --platform "$PLATFORM" --target agent -f "$HERE/Dockerfile" --build-context "prime_runtime=$PRIME_REF" \
  -t "$(name agent)" "${OUT[@]}" "$BACKEND"

pin() { if [[ -n "$REGISTRY" ]]; then echo "$REGISTRY/$1@$(docker buildx imagetools inspect "$(name "$1")" --format '{{.Manifest.Digest}}')"; else name "$1"; fi; }
cat <<EOF

Done. For deploy/cloud/.env on the Droplet:
CONTROL_IMAGE=$(pin control)
AGENT_IMAGE=$(pin agent)
EOF
