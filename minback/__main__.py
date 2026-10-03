"""CLI entry point: `python -m minback [run|serve]`."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .backup import run_backup
from .config import Config, ConfigError
from .metrics import Metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="minback", description="MariaDB backup to S3 and/or FTP")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "serve"],
        help="run: one backup then exit (default); serve: HTTP API + optional schedule",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for noisy in ("botocore", "boto3", "s3transfer", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        cfg = Config.from_env()
    except ConfigError as e:
        logging.error("configuration error: %s", e)
        return 2

    # Docker sends SIGTERM; turn it into a clean exit so temp files are removed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    if args.command == "serve":
        from .server import serve

        serve(cfg)
        return 0

    metrics = Metrics(cfg.db)
    result = run_backup(cfg, metrics)
    if cfg.pushgateway_url:
        metrics.push(cfg.pushgateway_url)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
