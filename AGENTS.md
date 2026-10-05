# Deployment workflow

The user wants the assistant to run deployments after requested bot changes.
After implementing and reviewing a change, run `python -m scripts.deploy` using
Python 3.12 with the project's dev dependencies. On this workstation,
`.venv.broken/bin/python` currently contains those dependencies; the directory
name is historical. Do not deploy with ad-hoc `yc version create` commands.

Production resource IDs are in `deploy/production.json`. The deployment script
checks the folder, runs lint/tests, uploads a candidate, tests authentication,
and only then moves the `production` tag. The gateway must never use `$latest`:
Yandex moves that tag automatically, even when another tag is supplied.

Preserve deployed environment values and Lockbox references. Do not print or
commit tokens, webhook secrets, `.env`, or Lockbox payloads. Do not reset the
Telegram webhook or drop pending updates during routine deployments.

The Cloudflare relay URL remains stable. Its `UPSTREAM_URL` must match the
gateway URL in `deploy/production.json`. Routine Python deployments do not
require editing Cloudflare. If changing the relay code, use its separate workflow.

For rollback use `python -m scripts.deploy --rollback VERSION_ID`; this tests
the target and moves `production`, not `$latest`. Do not delete old infrastructure
or rollback versions as part of a routine deployment.
