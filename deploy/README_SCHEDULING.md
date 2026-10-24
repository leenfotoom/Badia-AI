# Automatic scheduling (daily layer)

The templates call the checked-in daily CLI. Installing a schedule is a separate, explicit deployment action: validating
the definition does not register jobs, and the project ZIP does not change the host scheduler.

| Job | Cadence | Behaviour |
|---|---|---|
| `cli update` | every 6 h | Refreshes predictions only; it never retrains. A usable stale snapshot may complete normally, while provider fallback, unavailable data, or an uninitialised model returns a nonzero process result so the scheduler can retry and monitoring can alert. |
| `cli retrain` | weekly check | Checks local champion/dataset dates **before any network request**. If fewer than 30 days have elapsed or fewer than 21 potentially verified days exist, it exits without downloading. Only when due does it acquire verified increments, train a candidate, compare it on the fixed holdout, and apply promotion gates. |

Every mutating command (`update`, `acquire`, `train-local`, `bootstrap`, `retrain`, and `rollback`) uses a shared filesystem
operation lock. This prevents the update and retrain tasks from writing the cache, dataset, snapshots, or registry at the same
time even though they are separate scheduler entries. A lock conflict is an operational failure, not permission to start another
writer. Task Scheduler also rejects a second instance of either individual task.

## Acquisition and training are separate phases

Normal six-hour prediction refresh never retrains. For controlled maintenance the expensive network phase and local training
phase can be run independently:

```text
python -m backend.app.daily.cli acquire
python -m backend.app.daily.cli train-local
```

`acquire` writes resumable, verified local artifacts. `train-local` uses those artifacts without provider access. The recurring
`retrain` command is the safe orchestration command: it first checks whether work is due, then performs acquisition and local
candidate training only when justified. Do not schedule `acquire` and `train-local` independently unless an operator intends
to manage their ordering and inspect the acquired manifest.

Promotion gates require a sufficiently large holdout, valid metrics for every lead from Today through +7, skill over both
baselines, acceptable spatial validation, and—when replacing a champion—meaningful improvement on identical holdout rows.
Rejected candidates remain auditable and never replace the champion. Rollback remains available through
`python -m backend.app.daily.cli rollback`.

Only provider hosts in `config.py::ALLOWED_HOSTS` may be contacted; runtime input cannot add a source.

## Prerequisites

1. Run `setup_demo.ps1` on Windows, or create `.venv` at the project root and install `backend/requirements.txt`.
2. Run `python -m backend.app.daily.cli bootstrap` once and confirm that a real candidate passed every first-champion gate.
3. Run `python -m backend.app.daily.cli update` once.
4. Verify both `/api/daily/status` and `/api/health`. Health should report a ready daily model and snapshot; a healthy
   +16/+32 layer alone is intentionally not enough for overall status `ok`.

Recurring jobs do not silently invent a first model. Without a valid champion, update returns `not_initialized` and a nonzero
process result.

## Windows Task Scheduler

From PowerShell at the project root, validate the runtime, CLI command set, and Task Scheduler support without registering jobs:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\schedule_windows.ps1 -ValidateOnly
```

Then register or replace the two tasks:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\schedule_windows.ps1
```

The script prefers `.venv\Scripts\python.exe`, starts the first update five minutes after installation, runs missed jobs when the
computer returns, requires a network connection, rejects duplicate instances, and retries an abnormal result up to three times.
Its eight-hour execution limit accommodates a due incremental acquisition and candidate run. Pass an alternative interpreter
with `-PythonPath C:\absolute\path\python.exe` when required. Schedules use the Windows host timezone.

Inspect or remove the tasks:

```powershell
Get-ScheduledTask -TaskName "BADIA-Daily-*"
Unregister-ScheduledTask -TaskName "BADIA-Daily-Update","BADIA-Daily-Retrain-Check"
```

## Linux/macOS cron

Edit `deploy/badia-daily.crontab`: replace `/opt/badia` with the absolute project path and ensure `.venv` exists there. Copy
only the two job lines with `crontab -e`. Do **not** run `crontab deploy/badia-daily.crontab`, which would replace the user's
whole crontab. Cron uses the host timezone; configure it for `Asia/Amman` when the weekly 03:40 time must be Amman time.

The CLI lock is cross-platform, so the cron entries do not depend on a Linux-only `flock` utility.

## Monitoring

- Operational log: `data/daily/daily.log`; cron also appends to `data/daily/cron.log`.
- `python -m backend.app.daily.cli status` reports champion and retained versions without taking the mutation lock.
- `/api/daily/status` exposes generation time, nullable provider issue time, forecast reference date, retrieval/source
  freshness, provider status, last successful update, fallback state, model version, and snapshot age.
- `/api/health` reports the daily model and snapshot separately from the preserved +16/+32 outlook and degrades overall when
  the daily product is unavailable.
- A `skipped` weekly check is normal when cadence thresholds are unmet; it must not contact providers.
- A rejected candidate is also a successful safety outcome because the champion remains active.
- Alert on nonzero scheduler results, `fallback`/`expired`/`unavailable` state, stale source metadata, missing model artifacts,
  and a last-successful-update time that does not advance.
