# syntax=docker/dockerfile:1.7

# ── Stage 1: deps ─────────────────────────────────────────────────────────
FROM node:20-alpine AS deps

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

RUN corepack enable

WORKDIR /app
COPY packages/dashboard/package.json packages/dashboard/pnpm-lock.yaml* ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile || pnpm install


# ── Stage 2: builder ──────────────────────────────────────────────────────
FROM node:20-alpine AS builder

ENV NEXT_TELEMETRY_DISABLED=1 \
    PATH=/pnpm:$PATH

RUN corepack enable

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY packages/dashboard ./
RUN pnpm build


# ── Stage 3: runtime ──────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PATH=/pnpm:$PATH

RUN corepack enable && \
    addgroup --system --gid 10001 nodejs && \
    adduser --system --uid 10001 --ingroup nodejs nextjs

WORKDIR /app
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

CMD ["pnpm", "start"]
