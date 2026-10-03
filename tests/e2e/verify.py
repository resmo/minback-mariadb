"""Runs inside the minback container: check the latest backup on S3 and FTP.

Usage: python verify.py [create-bucket]
"""

import bz2
import ftplib
import io
import os
import sys

import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["OBJECT_SERVER"],
    aws_access_key_id=os.environ["OBJECT_ACCESS_KEY"],
    aws_secret_access_key=os.environ["OBJECT_SECRET_KEY"],
    region_name="us-east-1",
)
bucket = os.environ["OBJECT_BUCKET"]

if sys.argv[1:] == ["create-bucket"]:
    s3.create_bucket(Bucket=bucket)
    sys.exit(0)

MARKER = b"minback-e2e-marker"

keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=bucket).get("Contents", []))
assert keys, "no objects in bucket"
data = bz2.decompress(s3.get_object(Bucket=bucket, Key=keys[-1])["Body"].read())
assert MARKER in data, "S3 dump does not contain seed data"
print(f"S3 ok: {len(keys)} object(s), latest {keys[-1]} ({len(data)} bytes uncompressed)")

ftp = ftplib.FTP(os.environ["FTP_HOST"])
ftp.login(os.environ["FTP_USER"], os.environ["FTP_PASSWORD"])
names = sorted(n for n in ftp.nlst() if n.endswith(".sql.bz2"))
assert names, "no files on FTP"
buf = io.BytesIO()
ftp.retrbinary(f"RETR {names[-1]}", buf.write)
ftp.quit()
assert MARKER in bz2.decompress(buf.getvalue()), "FTP dump does not contain seed data"
print(f"FTP ok: {len(names)} file(s), latest {names[-1]}")
print(f"COUNTS s3={len(keys)} ftp={len(names)}")
