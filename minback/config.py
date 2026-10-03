"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(ValueError):
    pass


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from None


@dataclass(frozen=True)
class S3Target:
    server: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = "us-east-1"
    api_version: str = "S3v4"
    prefix: str = ""

    name = "s3"


@dataclass(frozen=True)
class FTPTarget:
    host: str
    user: str
    password: str
    port: int = 21
    directory: str = ""  # empty = login directory
    tls: bool = False

    name = "ftp"


@dataclass(frozen=True)
class Config:
    db: str
    db_password: str
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    date_format: str = "+%Y-%m-%d-%H%M"
    targets: tuple = field(default_factory=tuple)
    retry_attempts: int = 3
    retry_delay: float = 30.0
    notify_webhook_url: str = ""
    notify_on: str = "failure"
    listen_addr: str = "0.0.0.0:8080"
    api_token: str = ""
    schedule: str = ""
    pushgateway_url: str = ""
    tmp_dir: str = "/tmp"

    @property
    def strftime_format(self) -> str:
        # DATE_FORMAT historically used date(1) syntax with a leading "+".
        return self.date_format[1:] if self.date_format.startswith("+") else self.date_format

    @property
    def listen(self) -> tuple[str, int]:
        host, _, port = self.listen_addr.rpartition(":")
        return host or "0.0.0.0", int(port)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env
        get = lambda key, default="": env.get(key, "").strip() or default  # noqa: E731

        errors = []
        if not get("DB"):
            errors.append("DB is required")
        if not get("DB_PASSWORD"):
            errors.append("DB_PASSWORD is required")

        targets = []
        if get("OBJECT_SERVER"):
            missing = [k for k in ("OBJECT_ACCESS_KEY", "OBJECT_SECRET_KEY") if not get(k)]
            if missing:
                errors.append(f"S3 target: {', '.join(missing)} required when OBJECT_SERVER is set")
            api_version = get("OBJECT_API_VERSION", "S3v4")
            if api_version.lower() not in ("s3v4", "s3v2"):
                errors.append(f"OBJECT_API_VERSION must be S3v4 or S3v2, got {api_version!r}")
            targets.append(
                S3Target(
                    server=get("OBJECT_SERVER"),
                    bucket=get("OBJECT_BUCKET", "backups"),
                    access_key=get("OBJECT_ACCESS_KEY"),
                    secret_key=get("OBJECT_SECRET_KEY"),
                    region=get("OBJECT_REGION", "us-east-1"),
                    api_version=api_version,
                    prefix=get("OBJECT_PREFIX"),
                )
            )
        if get("FTP_HOST"):
            missing = [k for k in ("FTP_USER", "FTP_PASSWORD") if not get(k)]
            if missing:
                errors.append(f"FTP target: {', '.join(missing)} required when FTP_HOST is set")
            targets.append(
                FTPTarget(
                    host=get("FTP_HOST"),
                    user=get("FTP_USER"),
                    password=get("FTP_PASSWORD"),
                    port=_int(env, "FTP_PORT", 21),
                    directory=get("FTP_DIR"),
                    tls=_bool(get("FTP_TLS", "false")),
                )
            )
        if not targets:
            errors.append("no backup target configured: set OBJECT_SERVER and/or FTP_HOST")

        notify_on = get("NOTIFY_ON", "failure").lower()
        if notify_on not in ("failure", "always"):
            errors.append(f"NOTIFY_ON must be 'failure' or 'always', got {notify_on!r}")

        if errors:
            raise ConfigError("; ".join(errors))

        return cls(
            db=get("DB"),
            db_password=get("DB_PASSWORD"),
            db_host=get("DB_HOST", "localhost"),
            db_port=_int(env, "DB_PORT", 3306),
            db_user=get("DB_USER", "root"),
            date_format=get("DATE_FORMAT", "+%Y-%m-%d-%H%M"),
            targets=tuple(targets),
            retry_attempts=max(1, _int(env, "RETRY_ATTEMPTS", 3)),
            retry_delay=float(_int(env, "RETRY_DELAY", 30)),
            notify_webhook_url=get("NOTIFY_WEBHOOK_URL"),
            notify_on=notify_on,
            listen_addr=get("LISTEN_ADDR", "0.0.0.0:8080"),
            api_token=get("API_TOKEN"),
            schedule=get("SCHEDULE"),
            pushgateway_url=get("PUSHGATEWAY_URL"),
            tmp_dir=get("BACKUP_TMP_DIR", "/tmp"),
        )
