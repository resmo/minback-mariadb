# minback-mariadb
**Backup container for MariaDB to S3-compatible storage and FTP**

> [!NOTE]
> Inspired by [gh/SierraSoftworks/minback-mysql](https://github.com/SierraSoftworks/minback-mysql).

This container runs `mariadb-dump` for one database, compresses the dump with bzip2 and uploads it to
one or more targets: any S3-compatible object store (MinIO, RustFS, AWS S3, ...) and/or an FTP(S) server.

## Features
* Dumps a single MariaDB database (`--single-transaction`) to S3 and/or FTP
* Retries with exponential backoff, per step and per target
* Webhook notifications on failure (or every run)
* Two modes: a short-lived one-shot run, or a server with an HTTP API to trigger backups,
  an optional built-in cron schedule and a Prometheus `/metrics` endpoint
* ARM64 and AMD64 Docker images

> [!IMPORTANT]
> **Upgrading from v1:** all `MINIO_*` variables were renamed to `OBJECT_*`
> (`MINIO_SERVER` → `OBJECT_SERVER`, `MINIO_ACCESS_KEY` → `OBJECT_ACCESS_KEY`, ...).
> The old names are no longer read. Backups are now named `<DB>-<date>.sql.bz2` as before.

## Example
```sh
docker run --rm --env-file backup.env ghcr.io/resmo/minback-mariadb:main
```

#### `backup.env`
```
DB=my-db
DB_HOST=localhost
DB_PORT=3306
DB_USER=db-user
DB_PASSWORD=db-password

OBJECT_SERVER=https://s3.example.com
OBJECT_ACCESS_KEY=access-key
OBJECT_SECRET_KEY=secret-key
OBJECT_BUCKET=backups

# optional, in addition to (or instead of) S3
FTP_HOST=ftp.example.com
FTP_USER=backup
FTP_PASSWORD=ftp-password
```

The exit code is `0` when the backup reached every configured target, `1` when anything failed and
`2` on configuration errors.

## Server mode
```sh
docker run -d -p 8080:8080 --env-file backup.env -e API_TOKEN=s3cret -e SCHEDULE="0 3 * * *" \
  ghcr.io/resmo/minback-mariadb:main serve
```

| Endpoint | Description |
|---|---|
| `POST /backup` | Start a backup. `202` with `{"run_id": ...}`, `409` if one is already running, `401` if `API_TOKEN` is set and `Authorization: Bearer <token>` is missing or wrong. |
| `GET /status` | Whether a backup is running and the result of the last one. |
| `GET /metrics` | Prometheus metrics. |
| `GET /healthz` | Liveness check. |

```sh
curl -X POST -H "Authorization: Bearer s3cret" http://localhost:8080/backup
```

Only one backup runs at a time; a scheduled run is skipped if the previous one is still in progress.

### Metrics
All metrics carry a `db` label.

| Metric | Description |
|---|---|
| `minback_backup_runs_total{status}` | Runs by `success` / `failure` |
| `minback_backup_last_success_timestamp_seconds` | Unix time of the last successful backup |
| `minback_backup_last_failure_timestamp_seconds` | Unix time of the last failed backup |
| `minback_backup_last_duration_seconds` | Duration of the last run |
| `minback_backup_last_size_bytes` | Compressed size of the last dump |
| `minback_backup_running` | `1` while a backup is in progress |
| `minback_target_upload_failures_total{target}` | Uploads that failed after all retries, per target |

Example alert, no successful backup for two days:
```yaml
- alert: MariaDBBackupMissing
  expr: time() - minback_backup_last_success_timestamp_seconds > 2 * 86400
```

In one-shot mode, set `PUSHGATEWAY_URL` to push the same metrics to a Prometheus Pushgateway after each run.

## Configuration

This container is configured using environment variables. At least one target (S3 or FTP) is required.

#### Database

| Variable | Default | Description |
|---|---|---|
| `DB` | | Database name to back up (required). |
| `DB_HOST` | `localhost` | Database server host. |
| `DB_PORT` | `3306` | Database server port. |
| `DB_USER` | `root` | User to authenticate with. |
| `DB_PASSWORD` | | Password (required). Passed to `mariadb-dump` via an option file, not the command line. |
| `DATE_FORMAT` | `+%Y-%m-%d-%H%M` | Date format for file names, which are `<DB>-<date>.sql.bz2`. The leading `+` is optional. |

#### S3-compatible target (enabled when `OBJECT_SERVER` is set)

| Variable | Default | Description |
|---|---|---|
| `OBJECT_SERVER` | | Endpoint URL, e.g. `https://s3.example.com`. |
| `OBJECT_ACCESS_KEY` | | Access key (required with `OBJECT_SERVER`). |
| `OBJECT_SECRET_KEY` | | Secret key (required with `OBJECT_SERVER`). |
| `OBJECT_BUCKET` | `backups` | Bucket to store backups in. Must exist. |
| `OBJECT_PREFIX` | | Optional key prefix, e.g. `nightly/`. |
| `OBJECT_REGION` | `us-east-1` | Region. |
| `OBJECT_API_VERSION` | `S3v4` | Signature version, `S3v4` or `S3v2`. |

#### FTP target (enabled when `FTP_HOST` is set)

| Variable | Default | Description |
|---|---|---|
| `FTP_HOST` | | FTP server host. |
| `FTP_PORT` | `21` | FTP server port. |
| `FTP_USER` | | User (required with `FTP_HOST`). |
| `FTP_PASSWORD` | | Password (required with `FTP_HOST`). |
| `FTP_DIR` | | Directory to upload to. Empty means the login directory. Must exist. |
| `FTP_TLS` | `false` | Use explicit FTPS (`AUTH TLS`) with a protected data channel. |

#### Retries and notifications

| Variable | Default | Description |
|---|---|---|
| `RETRY_ATTEMPTS` | `3` | Attempts for the dump and for each target upload. |
| `RETRY_DELAY` | `30` | Seconds before the first retry; doubles on each further retry. |
| `NOTIFY_WEBHOOK_URL` | | URL to `POST` a JSON result to. |
| `NOTIFY_ON` | `failure` | `failure` or `always`. |

The webhook body contains a `text` field, so Slack and Mattermost incoming webhooks work directly:
```json
{"text": "Backup of shop FAILED: ftp: error: 530 Login incorrect.", "status": "failure", "db": "shop",
 "archive": "shop-2026-10-03-0300.sql.bz2", "size_bytes": 934, "duration_seconds": 8.0,
 "targets": {"s3": "ok", "ftp": "error: 530 Login incorrect."}, "error": null}
```

#### Server and runtime

| Variable | Default | Description |
|---|---|---|
| `LISTEN_ADDR` | `0.0.0.0:8080` | Server mode listen address. |
| `API_TOKEN` | | Bearer token required for `POST /backup`. Unauthenticated if empty. |
| `SCHEDULE` | | Cron expression for scheduled backups in server mode, e.g. `0 3 * * *` (container local time). |
| `PUSHGATEWAY_URL` | | One-shot mode: push metrics here after the run. |
| `BACKUP_TMP_DIR` | `/tmp` | The compressed dump is written here first, then uploaded to each target, then deleted. Needs free space for one compressed dump. |

## Nomad
See [`samples/nomad/backup.nomad`](samples/nomad/backup.nomad) for a periodic batch job and
[`samples/nomad/backup-server.nomad`](samples/nomad/backup-server.nomad) for server mode with a
Prometheus-tagged service.

## Development
```sh
uv sync                               # create .venv with runtime + dev dependencies
uv run pytest                         # unit tests
uv run ruff check . && uv run ruff format .
tests/e2e/run.sh                      # end-to-end: MariaDB, RustFS (S3), FTP, webhook via docker compose
DOCKER=podman COMPOSE=podman-compose tests/e2e/run.sh
```
