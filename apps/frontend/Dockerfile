# OmniTrade frontend — Next.js 14 (standalone output)
#
# Build context: **repository root**. Monorepo lives at /package.json
# with apps/frontend as the only workspace; the root lockfile is the
# source of truth for the frontend's exact dependency graph.
#
# Usage (via docker-compose.yml):
#   services.frontend.build.context: .
#   services.frontend.build.dockerfile: apps/frontend/Dockerfile

# ── deps: install workspace deps once using the root lockfile ─────────
FROM node:25-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/frontend/package.json ./apps/frontend/package.json
RUN npm ci --workspaces --include-workspace-root

# ── builder: produce .next/standalone ─────────────────────────────────
FROM node:25-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/frontend/node_modules ./apps/frontend/node_modules
COPY package.json package-lock.json ./
COPY apps/frontend ./apps/frontend
ENV NEXT_TELEMETRY_DISABLED=1
# Same-origin proxy strategy:
#   - Browser hits relative ``/api/*`` and ``/sse/*`` paths; the bundle's
#     baseUrl resolver defaults to ``""`` so client requests stay on the
#     same origin.
#   - The Next proxy declared in ``next.config.mjs`` rewrites those
#     requests to NEXT_PUBLIC_API_URL (the backend service inside the
#     Docker network). The destination is baked into ``.next/standalone``
#     at build time, so it MUST be set as a build arg here — runtime
#     ``docker-compose environment:`` is too late.
ARG NEXT_PUBLIC_API_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
WORKDIR /app/apps/frontend
RUN npm run build

# ── runner: minimal production image ──────────────────────────────────
FROM node:25-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# Next.js standalone bundle ships a minimal node_modules and server.js
COPY --from=builder --chown=nextjs:nodejs /app/apps/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/frontend/.next/static ./apps/frontend/.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "apps/frontend/server.js"]
