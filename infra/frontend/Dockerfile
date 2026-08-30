FROM node:22-alpine

WORKDIR /app

# package.json and the lockfile before the source: npm is the slow layer and it should
# not re-run because a component changed.
#
# `npm ci` rather than `npm install` — it installs exactly the lockfile, fails if
# package.json and the lockfile disagree, and never silently updates a transitive
# dependency mid-build. The lockfile is committed for this reason.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
