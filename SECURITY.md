# Security policy

## Supported versions

The latest release, and `main`. A fix lands on `main` and ships in the next release; an
older release is not patched.

## Reporting a vulnerability

Please do not open a public issue. Report it privately through GitHub: the repository's
**Security** tab, then **Report a vulnerability**. Say what an attacker could do, and how
to reproduce it.

## What the defaults assume

SpeakLab is built to run on one machine, for the person using it. Some defaults are right
for that and wrong anywhere else:

- **The API signs sessions with a built-in development key until `JWT_SECRET` is set**,
  and says so in its startup log every time. Set it before the API can be reached from
  anywhere but your own machine.
- **Accounts have no password reset, no email verification and no login rate limiting.**
- **The database has a development password, and the model services have no
  authentication.** Every port is published on `127.0.0.1` only, so neither is offered to
  the network the machine is on. Publishing one more widely changes that.
- **Ollama on Linux has to listen on `0.0.0.0`** for the containers to reach it, which
  also exposes it to your network. Firewall port 11434.

## What is in place

- **Accounts.** Passwords are hashed with Argon2id; the session is a JWT in an httpOnly
  cookie, verified against one algorithm; another account's data answers 404, never 403;
  and a wrong password takes as long to refuse as an unknown email, so the login endpoint
  does not reveal who has an account.
- **Containers.** Every service runs as an unprivileged account. Each image applies the
  security fixes its distribution has published since its base was built, and carries
  nothing it does not run.
- **Dependencies.** Python requirements are pinned exactly and the frontend's lockfile is
  committed. Dependabot proposes updates weekly, and a security update for each published
  vulnerability, for everything but the frontend, whose lockfile its updater cannot yet
  write; CI audits the frontend's packages every week instead. pnpm installs no release
  less than a day old, none published with weaker evidence of its origin than an earlier
  release of the same package, and runs no dependency's install script unless it is
  allowed by name.
- **CI.** A Trivy scan fails a pull request on a HIGH or CRITICAL vulnerability that has
  a fixed release, on a Dockerfile that runs as root, and on a secret in the tree, and
  runs again every Monday on `main`, so a vulnerability published since the last change
  fails it with nobody pushing. Every action is pinned to a commit. Every workflow's token
  is read-only but two jobs': the release job can create a release, and the Pages job can
  publish the site. `main` takes a change only through a pull request, squash-merged, with
  every check green, and cannot be force-pushed.
