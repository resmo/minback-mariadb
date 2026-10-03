"""HTTP API: trigger backups, report status, expose Prometheus metrics."""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .backup import run_backup
from .config import Config
from .metrics import Metrics

log = logging.getLogger(__name__)


class BackupService:
    """Runs at most one backup at a time in a background thread."""

    def __init__(self, cfg: Config, metrics: Metrics, runner=run_backup):
        self.cfg = cfg
        self.metrics = metrics
        self.runner = runner
        self._lock = threading.Lock()
        self.current_id: str | None = None
        self.last_result = None
        self.last_id: str | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def trigger(self, source: str) -> str | None:
        """Start a backup; returns its run id, or None if one is already running."""
        if not self._lock.acquire(blocking=False):
            return None
        run_id = uuid.uuid4().hex[:12]
        self.current_id = run_id
        log.info("Backup %s triggered by %s", run_id, source)
        threading.Thread(target=self._run, args=(run_id,), daemon=True, name=f"backup-{run_id}").start()
        return run_id

    def _run(self, run_id: str) -> None:
        try:
            self.last_result = self.runner(self.cfg, self.metrics)
            self.last_id = run_id
        except Exception:
            log.exception("Backup %s crashed", run_id)
        finally:
            self.current_id = None
            self._lock.release()

    def status(self) -> dict:
        return {
            "db": self.cfg.db,
            "running": self.running,
            "current_run": self.current_id,
            "last_run": self.last_id,
            "last_result": self.last_result.to_dict() if self.last_result else None,
            "schedule": self.cfg.schedule or None,
        }


def make_handler(service: BackupService):
    token = service.cfg.api_token

    class Handler(BaseHTTPRequestHandler):
        server_version = "minback"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        def _send(self, code: int, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else (json.dumps(body) + "\n").encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                self._send(200, {"status": "ok"})
            elif path == "/status":
                self._send(200, service.status())
            elif path == "/metrics":
                self._send(200, generate_latest(service.metrics.registry), CONTENT_TYPE_LATEST)
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path != "/backup":
                self._send(404, {"error": "not found"})
                return
            if token:
                auth = self.headers.get("Authorization", "")
                if not hmac.compare_digest(auth.encode(), f"Bearer {token}".encode()):
                    self._send(401, {"error": "unauthorized"})
                    return
            run_id = service.trigger(source=f"http {self.address_string()}")
            if run_id is None:
                self._send(409, {"error": "backup already running", "current_run": service.current_id})
            else:
                self._send(202, {"run_id": run_id})

    return Handler


def scheduler(service: BackupService, expression: str, stop: threading.Event) -> None:
    from croniter import croniter

    it = croniter(expression, datetime.now().astimezone())
    while not stop.is_set():
        nxt = it.get_next(float)
        log.info("Next scheduled backup at %s", datetime.fromtimestamp(nxt).isoformat(timespec="seconds"))
        if stop.wait(max(0.0, nxt - time.time())):
            return
        if service.trigger(source="schedule") is None:
            log.warning("Scheduled backup skipped: previous backup still running")


def serve(cfg: Config) -> None:
    if cfg.schedule:
        from croniter import croniter

        if not croniter.is_valid(cfg.schedule):
            raise SystemExit(f"invalid SCHEDULE cron expression: {cfg.schedule!r}")
    if not cfg.api_token:
        log.warning("API_TOKEN not set: POST /backup is unauthenticated")

    service = BackupService(cfg, Metrics(cfg.db))
    stop = threading.Event()
    if cfg.schedule:
        threading.Thread(
            target=scheduler, args=(service, cfg.schedule, stop), daemon=True, name="scheduler"
        ).start()

    httpd = ThreadingHTTPServer(cfg.listen, make_handler(service))
    log.info("Listening on %s:%d", *cfg.listen)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()
