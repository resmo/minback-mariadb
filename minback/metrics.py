"""Prometheus metrics."""

from __future__ import annotations

import logging

from prometheus_client import CollectorRegistry, Counter, Gauge, push_to_gateway

log = logging.getLogger(__name__)


class Metrics:
    def __init__(self, db: str, registry: CollectorRegistry | None = None):
        self.db = db
        self.registry = registry or CollectorRegistry()
        r = self.registry
        self.runs = Counter("minback_backup_runs", "Backup runs by result", ["db", "status"], registry=r)
        self.last_success = Gauge(
            "minback_backup_last_success_timestamp_seconds",
            "Unix time of the last successful backup",
            ["db"],
            registry=r,
        )
        self.last_failure = Gauge(
            "minback_backup_last_failure_timestamp_seconds",
            "Unix time of the last failed backup",
            ["db"],
            registry=r,
        )
        self.last_duration = Gauge(
            "minback_backup_last_duration_seconds", "Duration of the last backup run", ["db"], registry=r
        )
        self.last_size = Gauge(
            "minback_backup_last_size_bytes", "Compressed size of the last dump", ["db"], registry=r
        )
        self.running = Gauge("minback_backup_running", "1 while a backup is in progress", ["db"], registry=r)
        self.upload_failures = Counter(
            "minback_target_upload_failures",
            "Failed uploads per target (after retries)",
            ["db", "target"],
            registry=r,
        )
        # Initialise label sets so series exist (as 0) before the first run.
        for status in ("success", "failure"):
            self.runs.labels(db, status)
        for g in (self.last_success, self.last_failure, self.last_duration, self.last_size, self.running):
            g.labels(db)

    def record(self, result) -> None:
        db = self.db
        self.runs.labels(db, "success" if result.success else "failure").inc()
        (self.last_success if result.success else self.last_failure).labels(db).set(result.finished_at)
        self.last_duration.labels(db).set(result.duration_seconds)
        if result.size_bytes:
            self.last_size.labels(db).set(result.size_bytes)
        for target, status in result.targets.items():
            if status != "ok":
                self.upload_failures.labels(db, target).inc()

    def push(self, gateway: str) -> None:
        try:
            push_to_gateway(gateway, job="minback", registry=self.registry, grouping_key={"db": self.db})
        except Exception as e:
            log.error("pushing metrics to %s failed: %s", gateway, e)
