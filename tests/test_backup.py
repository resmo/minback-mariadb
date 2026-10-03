import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from prometheus_client import generate_latest

from minback import notify
from minback.backup import run_backup
from minback.config import Config
from minback.metrics import Metrics


def fake_dump(cfg, path):
    with open(path, "wb") as f:
        f.write(b"x" * 42)
    return 42


class Uploads:
    def __init__(self, fail=()):
        self.fail = dict.fromkeys(fail, True)
        self.calls = []

    def __call__(self, target, path, name):
        self.calls.append((target.name, name, os.path.getsize(path)))
        if self.fail.get(target.name):
            raise ConnectionError(f"{target.name} down")
        return f"{target.name}://{name}"


def no_sleep(_):
    pass


def test_success_uploads_to_all_targets(cfg, tmp_path):
    uploads = Uploads()
    metrics = Metrics(cfg.db)
    result = run_backup(cfg, metrics, dump_fn=fake_dump, upload_fn=uploads, sleep=no_sleep)
    assert result.success
    assert result.targets == {"s3": "ok", "ftp": "ok"}
    assert result.size_bytes == 42
    assert [c[0] for c in uploads.calls] == ["s3", "ftp"]
    assert all(c[2] == 42 for c in uploads.calls)
    assert list(tmp_path.iterdir()) == [], "spool file must be removed"
    text = generate_latest(metrics.registry).decode()
    assert 'minback_backup_runs_total{db="shop",status="success"} 1.0' in text
    assert 'minback_backup_last_size_bytes{db="shop"} 42.0' in text
    assert 'minback_backup_running{db="shop"} 0.0' in text


def test_one_target_failing_fails_run_but_others_upload(cfg, tmp_path):
    uploads = Uploads(fail=["ftp"])
    metrics = Metrics(cfg.db)
    result = run_backup(cfg, metrics, dump_fn=fake_dump, upload_fn=uploads, sleep=no_sleep)
    assert not result.success
    assert result.targets["s3"] == "ok"
    assert result.targets["ftp"] == "error: ftp down"
    # s3 uploaded once, ftp retried RETRY_ATTEMPTS times, dump not repeated
    assert [c[0] for c in uploads.calls] == ["s3", "ftp", "ftp", "ftp"]
    assert list(tmp_path.iterdir()) == []
    text = generate_latest(metrics.registry).decode()
    assert 'minback_backup_runs_total{db="shop",status="failure"} 1.0' in text
    assert 'minback_target_upload_failures_total{db="shop",target="ftp"} 1.0' in text


def test_dump_failure_skips_uploads(cfg):
    attempts = []

    def bad_dump(cfg, path):
        attempts.append(1)
        raise RuntimeError("access denied")

    uploads = Uploads()
    result = run_backup(cfg, None, dump_fn=bad_dump, upload_fn=uploads, sleep=no_sleep)
    assert not result.success
    assert result.error == "dump failed: access denied"
    assert len(attempts) == 3
    assert uploads.calls == []


@pytest.fixture
def webhook():
    received = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/hook", received
    srv.shutdown()


@pytest.mark.parametrize(
    "notify_on,fail,expected",
    [
        ("failure", True, 1),
        ("failure", False, 0),
        ("always", False, 1),
    ],
)
def test_webhook(cfg, webhook, notify_on, fail, expected):
    url, received = webhook
    cfg = Config(**{**cfg.__dict__, "notify_webhook_url": url, "notify_on": notify_on})
    run_backup(cfg, None, dump_fn=fake_dump, upload_fn=Uploads(fail=["s3"] if fail else []), sleep=no_sleep)
    assert len(received) == expected
    if expected:
        body = received[0]
        assert body["status"] == ("failure" if fail else "success")
        assert body["db"] == "shop"
        assert "shop" in body["text"]
        if fail:
            assert body["targets"]["s3"] == "error: s3 down"
            assert "FAILED" in body["text"]


def test_webhook_errors_are_swallowed(cfg):
    cfg = Config(**{**cfg.__dict__, "notify_webhook_url": "http://127.0.0.1:9/nope"})
    result = run_backup(cfg, None, dump_fn=fake_dump, upload_fn=Uploads(fail=["s3"]), sleep=no_sleep)
    assert not result.success


def test_notify_payload_on_dump_error(cfg):
    from minback.backup import Result

    r = Result(db="shop", archive="a", started_at=0, finished_at=1, error="dump failed: boom")
    assert notify.payload(r)["text"] == "Backup of shop FAILED: dump failed: boom"
