# Local development image for the Studio (Vite dev server with the /api proxy).
FROM node:22-slim

RUN corepack enable
WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/studio/package.json apps/studio/
COPY packages/api-client/package.json packages/api-client/
RUN pnpm install --frozen-lockfile

COPY . .

EXPOSE 5173
CMD ["pnpm", "--filter", "@studio/studio", "dev"]
