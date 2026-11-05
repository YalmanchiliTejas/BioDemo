# Linux build of the Prime SDK at /opt/prime-agent, consumed by the agent stage of ./Dockerfile.
# Build context is the Prime checkout (e.g. ~/Desktop/prime-agent-bio); see build-images.sh.
FROM node:22.21-bookworm-slim AS build
WORKDIR /opt/prime-agent
COPY . .
# Install and build for Linux; the checkout's macOS node_modules are excluded by the .dockerignore.
RUN npm ci --no-audit --no-fund && npm run build \
    && test -f packages/coding-agent/dist/index.js

FROM node:22.21-bookworm-slim
COPY --from=build /opt/prime-agent /opt/prime-agent
