"""Webhook notifications."""

from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)


def should_notify(notify_on: str, success: bool) -> bool:
    return notify_on == "always" or not success


def payload(result) -> dict:
    if result.success:
        text = f"Backup of {result.db} succeeded: {result.archive} ({result.size_bytes} bytes)"
    else:
        failed = {k: v for k, v in result.targets.items() if v != "ok"}
        detail = result.error or ", ".join(f"{k}: {v}" for k, v in failed.items())
        text = f"Backup of {result.db} FAILED: {detail}"
    return {
        "text": text,
        "status": "success" if result.success else "failure",
        "db": result.db,
        "archive": result.archive,
        "size_bytes": result.size_bytes,
        "duration_seconds": round(result.duration_seconds, 3),
        "targets": result.targets,
        "error": result.error,
    }


def send(url: str, result, timeout: float = 10) -> None:
    """POST the result as JSON. Notification errors are logged, never raised."""
    body = json.dumps(payload(result)).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
    except Exception as e:
        log.error("webhook notification failed: %s", e)
