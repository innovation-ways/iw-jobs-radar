# Frontend image (ADR-079): the static Vite build served by nginx, which also proxies the API so the
# browser sees one origin (no CORS). Build context: this directory.
FROM node:22-alpine AS build
WORKDIR /app
# corepack reads the pnpm version pinned in package.json ("packageManager").
RUN corepack enable
# Dependencies first so this layer is cached until the lockfile changes.
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Unprivileged nginx: runs as a non-root user and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
