# Local development image for the Studio (Vite dev server with the /api proxy).

# Install stage: pnpm (through corepack) installs the locked workspace dependencies.
FROM node:22-slim AS install

RUN corepack enable
WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/studio/package.json apps/studio/
COPY packages/api-client/package.json packages/api-client/
RUN pnpm install --frozen-lockfile

COPY . .

# Runtime stage: Node and the installed workspace only. npm, corepack and the pnpm release it
# caches are not needed to run Vite, and the Trivy gate (security.yml) rejects their known CVEs.
FROM node:22-slim

RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
    /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

COPY --from=install --chown=node:node /app /app

USER node
WORKDIR /app/apps/studio

EXPOSE 5173
CMD ["node", "/app/node_modules/vite/bin/vite.js", "--host", "0.0.0.0"]
