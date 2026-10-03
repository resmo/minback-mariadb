"""S3-compatible object storage (MinIO, RustFS, AWS, ...)."""

from __future__ import annotations

import boto3
from botocore.config import Config as BotoConfig

from ..config import S3Target


def client(t: S3Target):
    signature = "s3v4" if t.api_version.lower() == "s3v4" else "s3"
    return boto3.client(
        "s3",
        endpoint_url=t.server,
        aws_access_key_id=t.access_key,
        aws_secret_access_key=t.secret_key,
        region_name=t.region,
        config=BotoConfig(signature_version=signature, s3={"addressing_style": "path"}),
    )


def upload(t: S3Target, path: str, name: str) -> str:
    key = f"{t.prefix.strip('/')}/{name}" if t.prefix.strip("/") else name
    # upload_file aborts the multipart upload itself on failure, so no partial
    # object is left behind.
    client(t).upload_file(path, t.bucket, key)
    return f"s3://{t.bucket}/{key}"
