"""Upload targets. Each exposes upload(target_config, path, name)."""

from __future__ import annotations

from ..config import FTPTarget, S3Target


def upload(target, path: str, name: str) -> str:
    """Upload the file at path as `name`; returns the remote location."""
    if isinstance(target, S3Target):
        from . import s3

        return s3.upload(target, path, name)
    if isinstance(target, FTPTarget):
        from . import ftp

        return ftp.upload(target, path, name)
    raise TypeError(f"unknown target {target!r}")
