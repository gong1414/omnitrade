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
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/frontend/package.json ./apps/frontend/package.json
RUN npm ci --workspaces --include-workspace-root

# ── builder: produce .next/standalone ─────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/frontend/node_modules ./apps/frontend/node_modules
COPY package.json package-lock.json ./
COPY apps/frontend ./apps/frontend
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/frontend
RUN npm run build

# ── runner: minimal production image ──────────────────────────────────
FROM node:20-alpine AS runner
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
