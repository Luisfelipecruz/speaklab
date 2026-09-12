# The frontend, served by the Next.js development server with the source bind-mounted
# over /app (docker-compose.yml). Build context is frontend/.
FROM node:24.21.0-alpine3.24

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
