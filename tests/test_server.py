import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from minback.backup import Result
from minback.config import Config
from minback.metrics import Metrics
from minback.server import BackupService, make_handler


class GatedRunner:
    """Backup runner that blocks until released, to test concurrency."""

    def __init__(self):
        self.release = threading.Event()
        self.done = threading.Event()

    def __call__(self, cfg, metrics):
        self.release.wait(5)
        r = Result(db=cfg.db, archive="a", started_at=1, finished_at=2, size_bytes=7, targets={"s3": "ok"})
        metrics.record(r)
        self.done.set()
        return r


@pytest.fixture
def server(cfg):
    cfg = Config(**{**cfg.__dict__, "api_token": "t0ken"})
    runner = GatedRunner()
    service = BackupService(cfg, Metrics(cfg.db), runner=runner)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", runner
    runner.release.set()
    httpd.shutdown()


def call(url, method="GET", token=None):
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except HTTPError as e:
        return e.code, e.read().decode()


def test_healthz(server):
    base, _ = server
    assert call(base + "/healthz")[0] == 200
    assert call(base + "/nope")[0] == 404


def test_trigger_requires_token(server):
    base, _ = server
    assert call(base + "/backup", "POST")[0] == 401
    assert call(base + "/backup", "POST", token="wrong")[0] == 401


def test_trigger_conflict_status_and_metrics(server):
    base, runner = server
    code, body = call(base + "/backup", "POST", token="t0ken")
    assert code == 202
    run_id = json.loads(body)["run_id"]

    code, body = call(base + "/backup", "POST", token="t0ken")
    assert code == 409
    assert json.loads(body)["current_run"] == run_id

    status = json.loads(call(base + "/status")[1])
    assert status["running"] is True and status["current_run"] == run_id

    runner.release.set()
    assert runner.done.wait(5)
    for _ in range(50):  # let the worker thread release the lock
        status = json.loads(call(base + "/status")[1])
        if not status["running"]:
            break
        threading.Event().wait(0.02)
    assert status["running"] is False
    assert status["last_run"] == run_id
    assert status["last_result"]["success"] is True

    metrics = call(base + "/metrics")[1]
    assert 'minback_backup_runs_total{db="shop",status="success"} 1.0' in metrics
    assert 'minback_backup_last_success_timestamp_seconds{db="shop"} 2.0' in metrics
