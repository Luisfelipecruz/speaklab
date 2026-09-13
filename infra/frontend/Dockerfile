# The frontend, in two shapes built from one install. Build context is frontend/.
#
#   runner  the default stack's: `next build`'s standalone server, and nothing else — no
#           source, no build or test tools, no package manager
#   dev     the development server over the bind-mounted source (the `dev` profile in
#           docker-compose.yml); the frontend's tests, types and lint run in it too

FROM node:24.21.0-alpine3.24 AS base

# The security fixes Alpine has published since the base image was built.
RUN apk upgrade --no-cache

WORKDIR /app

# The manifest, the lockfile and pnpm's settings before the source: installing is the
# slow layer, and it should not re-run because a component changed.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# pnpm at the version package.json's `packageManager` names, installed once for every
# account. npm and corepack are then removed: the image needs one package manager, and
# the ones it does not use carry dependencies of their own that a scanner rightly reports.
RUN npm install --global "$(node -p "require('./package.json').packageManager")" \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /root/.npm \
    && chown -R node:node /app

# The base image's own unprivileged account, from here on.
USER node

# `--frozen-lockfile` installs exactly the lockfile and fails if package.json and the
# lockfile disagree. Before it downloads anything, pnpm checks every entry against the
# release-age and trust settings in pnpm-workspace.yaml, and it runs no dependency's
# install script that the same file does not allow. The store pnpm installs from and the
# registry metadata it cached are then deleted in the same layer: node_modules is what
# runs, and the two beside it would more than double the layer.
RUN pnpm install --frozen-lockfile \
    && rm -rf "$(pnpm store path)" "$HOME/.cache"

COPY --chown=node:node . .


FROM base AS dev

# .next exists in the image so the anonymous volume mounted over it starts out owned by
# the same account.
RUN mkdir -p .next

EXPOSE 3000

# busybox wget, because the image has no curl and adding one to answer a health check is
# a poor trade; --spider requests the page and downloads nothing. `next dev` compiles the
# first route on demand, so the first answer takes seconds, and the start period covers it.
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=60s \
    CMD wget -q --spider http://localhost:3000 || exit 1

CMD ["pnpm", "run", "dev"]


FROM base AS build

# The browser's address for the API is compiled into the client bundle by `next build`,
# so it is a build argument; the server's address (INTERNAL_API_URL) is read at runtime.
ARG NEXT_PUBLIC_API_URL=http://localhost:8002
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_OPTIONS=--no-network-family-autoselection

# The fonts are fetched here, once; NODE_OPTIONS stops Node racing IPv4 against IPv6 for
# them, which fails on networks with no IPv6 route.
RUN pnpm run build


FROM node:24.21.0-alpine3.24 AS runner

# Alpine's fixes, and no package manager at all: the standalone server needs none.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /root/.npm

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# The traced server with the modules it imports, and the static assets it serves.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=20s \
    CMD wget -q --spider http://localhost:3000 || exit 1

CMD ["node", "server.js"]
