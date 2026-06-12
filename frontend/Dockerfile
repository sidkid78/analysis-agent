# Quick Data frontend — Next.js (standalone output).
# Multi-stage build for a small runtime image.
FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@10.12.4 --activate

# --- dependencies ---
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# --- build ---
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* is inlined at build time. These are the URLs the browser (on the
# host) uses to reach the backends — so they point at the host-mapped API ports.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8020
ARG NEXT_PUBLIC_SMARTDEV_API_BASE=http://localhost:8030
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_SMARTDEV_API_BASE=$NEXT_PUBLIC_SMARTDEV_API_BASE \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# --- runtime ---
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
