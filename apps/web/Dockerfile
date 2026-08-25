FROM node:20-slim AS builder
WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci && npm install --no-save @tailwindcss/oxide-linux-x64-gnu lightningcss-linux-x64-gnu @next/swc-linux-x64-gnu

COPY apps/web ./
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000

CMD ["npm", "start"]
