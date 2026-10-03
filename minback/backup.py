"""One backup run: dump, then upload to every target."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import notify
from .config import Config
from .dump import dump
from .retry import retry
from .targets import upload

log = logging.getLogger(__name__)


@dataclass
class Result:
    db: str
    archive: str
    started_at: float
    finished_at: float = 0.0
    size_bytes: int = 0
    targets: dict = field(default_factory=dict)  # target name -> "ok" | "error: ..."
    error: str | None = None  # set when the dump itself failed

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.targets) and all(v == "ok" for v in self.targets.values())

    @property
    def duration_seconds(self) -> float:
        return self.finished_at - self.started_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["success"] = self.success
        d["duration_seconds"] = round(self.duration_seconds, 3)
        return d


def archive_name(cfg: Config, now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{cfg.db}-{now.strftime(cfg.strftime_format)}.sql.bz2"


def run_backup(cfg: Config, metrics=None, *, dump_fn=dump, upload_fn=upload, sleep=time.sleep) -> Result:
    name = archive_name(cfg)
    result = Result(db=cfg.db, archive=name, started_at=time.time())
    if metrics:
        metrics.running.labels(cfg.db).set(1)

    fd, path = tempfile.mkstemp(prefix=f"minback-{cfg.db}-", suffix=".sql.bz2", dir=cfg.tmp_dir)
    os.close(fd)
    try:
        log.info("Dumping %s from %s:%s as %s", cfg.db, cfg.db_host, cfg.db_port, cfg.db_user)
        try:
            result.size_bytes = retry(
                lambda: dump_fn(cfg, path), cfg.retry_attempts, cfg.retry_delay, "dump", sleep=sleep
            )
        except Exception as e:
            result.error = f"dump failed: {e}"
        else:
            log.info("Dump complete: %d bytes compressed", result.size_bytes)
            for target in cfg.targets:
                try:
                    location = retry(
                        lambda t=target: upload_fn(t, path, name),
                        cfg.retry_attempts,
                        cfg.retry_delay,
                        f"upload to {target.name}",
                        sleep=sleep,
                    )
                    log.info("Uploaded to %s", location)
                    result.targets[target.name] = "ok"
                except Exception as e:
                    result.targets[target.name] = f"error: {e}"
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        result.finished_at = time.time()
        if metrics:
            metrics.running.labels(cfg.db).set(0)

    if metrics:
        metrics.record(result)
    if result.success:
        log.info("Backup complete in %.1fs", result.duration_seconds)
    else:
        log.error("Backup failed: %s", result.error or result.targets)
    if cfg.notify_webhook_url and notify.should_notify(cfg.notify_on, result.success):
        notify.send(cfg.notify_webhook_url, result)
    return result
