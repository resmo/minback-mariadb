# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Docker image that backs up one MariaDB database: `mariadb-dump` → bzip2 → upload to one or more targets (S3-compatible storage via boto3, and/or FTP/FTPS via ftplib). Written in Python 3 (the `minback` package); the image is based on `mariadb:lts`, which provides `mariadb-dump`. Two modes: `run` (one-shot, default `CMD`, used by the Nomad periodic batch job) and `serve` (HTTP API + optional cron schedule + Prometheus metrics). README.md documents every env var.

## Commands

```sh
uv sync                                           # .venv with runtime + dev deps
uv run pytest                                     # all unit tests
uv run pytest tests/test_backup.py -k webhook     # single test(s)
uv run ruff check . && uv run ruff format .       # lint + format (CI runs both, format with --check)
uv add <pkg> / uv add --dev <pkg>                 # change deps; commit pyproject.toml and uv.lock
tests/e2e/run.sh                                  # e2e via docker compose: MariaDB, RustFS (S3), FTP, webhook receiver
DOCKER=podman COMPOSE=podman-compose tests/e2e/run.sh   # same with podman
docker build -t minback-mariadb:dev .
```

The e2e test builds `minback-mariadb:dev`, runs a successful one-shot backup, a failure (wrong FTP password → retries, exit 1, failure webhook), then serve mode via the API, and checks the uploaded dumps with `tests/e2e/verify.py` (run inside the minback container). MinIO is no longer publicly pullable, so RustFS is used as the S3 server.

## Architecture

- `config.py`: `Config.from_env()` is the single source of truth for env vars and defaults (the Dockerfile has no `ENV` defaults). A target is enabled when its host var is set (`OBJECT_SERVER`, `FTP_HOST`); `Config.targets` is a tuple of `S3Target` / `FTPTarget`. Validation errors are collected and raised together as `ConfigError` (exit code 2).
- `backup.run_backup()` orchestrates one run. It spools the compressed dump to a temp file in `BACKUP_TMP_DIR` because retries and multiple targets each need to re-read it. The dump and each target upload are retried independently via `retry.retry()`. The run succeeds only if every target got the file. It then records metrics and sends the webhook. `dump_fn`, `upload_fn` and `sleep` are injectable for tests.
- `dump.py` passes the DB password via a temporary 0600 `--defaults-extra-file` (must stay the first argument), never on the command line. stderr goes to a temp file to avoid pipe deadlocks.
- `targets/__init__.upload()` dispatches on the target dataclass type. To add a target: add a dataclass + env parsing in `config.py`, a module in `targets/`, a branch in the dispatcher, and README docs. Targets must clean up partial uploads on failure.
- `server.py`: `BackupService` allows one backup at a time (non-blocking lock → HTTP 409) and runs it in a background thread. The cron scheduler thread uses the same `trigger()`.
- `metrics.py`: each `Metrics` instance has its own `CollectorRegistry` (keeps tests isolated). In `run` mode it can push to a Pushgateway.

## Conventions

- v2 renamed `MINIO_*` → `OBJECT_*` without fallback. Don't reintroduce `MINIO_*` reads.
- Archive names are `<DB>-<strftime(DATE_FORMAT)>.sql.bz2`. `DATE_FORMAT` accepts date(1) syntax with a leading `+` for v1 compatibility.
- Project metadata, deps (dev deps in the `dev` dependency group), ruff and pytest config live in `pyproject.toml`; `uv.lock` pins versions and is used with `--frozen`/`--locked` in the Dockerfile and CI. Dependabot updates it (`uv` ecosystem).
- The Dockerfile installs with uv against the base image's system `python3` (`UV_PYTHON_DOWNLOADS=never`) into `/opt/venv`; uv is only bind-mounted at build time. Entry point is the `minback` console script.

## CI / release

`.github/workflows/docker.yml`: `unit` (ruff + pytest via uv) and `e2e` run on every PR and push. A PR then builds the multi-arch image (`linux/arm64,linux/amd64`). A push to `main` or a `v*` tag pushes to `ghcr.io/resmo/minback-mariadb` (tags: branch, `{{version}}`, `{{major}}.{{minor}}`). Nomad samples in `samples/nomad/` (batch and server mode) force-pull unless the version starts with `v`.
