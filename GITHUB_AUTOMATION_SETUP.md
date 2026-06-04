# GitHub Automation Setup

The repo is configured to send two daily emails from GitHub Actions:

- Morning digest: `watcher.yml` at `12:00 UTC`
- Evening digest: `boards.yml` at `22:00 UTC`

Those times equal `8:00 AM` and `6:00 PM` in `America/New_York` during daylight saving time. In standard time, GitHub cron will run one hour earlier locally because GitHub schedules use UTC.

## Required GitHub Secrets

Add these repository secrets in GitHub:

- `EMAIL_USER`
- `EMAIL_APP_PASSWORD`
- `ALERT_TO_EMAIL`

Use these values:

- `EMAIL_USER`: your Gmail address
- `EMAIL_APP_PASSWORD`: your Gmail app password
- `ALERT_TO_EMAIL`: the inbox where you want alerts delivered

## Where To Add Them

In GitHub:

1. Open the repository.
2. Go to `Settings`.
3. Go to `Secrets and variables` -> `Actions`.
4. Create the three secrets above.

## Manual Trigger

You can also trigger either workflow manually from the `Actions` tab with `workflow_dispatch`.
