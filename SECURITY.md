# Security policy

## Supported versions

Only the latest commit on `main`. SpeakLab has no tagged releases.

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
- **Ollama on Linux has to listen on `0.0.0.0`** for the containers to reach it, which
  also exposes it to your network. Firewall port 11434.

What is in place: passwords are hashed with Argon2id; the session is a JWT in an httpOnly
cookie; another account's data answers 404, never 403; and a wrong password takes as long
to refuse as an unknown email, so the login endpoint does not reveal who has an account.
