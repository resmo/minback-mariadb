import ftplib
from unittest import mock

import boto3
import pytest
from moto import mock_aws

from minback.config import FTPTarget, S3Target
from minback.targets import upload


@pytest.fixture
def archive(tmp_path):
    p = tmp_path / "a.sql.bz2"
    p.write_bytes(b"data")
    return str(p)


@mock_aws
@pytest.mark.parametrize("prefix,key", [("", "shop.sql.bz2"), ("/nightly/", "nightly/shop.sql.bz2")])
def test_s3_upload(archive, prefix, key):
    t = S3Target(server=None, bucket="backups", access_key="ak", secret_key="sk", prefix=prefix)
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="backups")
    assert upload(t, archive, "shop.sql.bz2") == f"s3://backups/{key}"
    obj = boto3.client("s3", region_name="us-east-1").get_object(Bucket="backups", Key=key)
    assert obj["Body"].read() == b"data"


@pytest.mark.parametrize("tls", [False, True])
def test_ftp_upload(archive, tls):
    t = FTPTarget(host="ftp.local", user="u", password="p", port=2121, directory="/bk", tls=tls)
    cls = "FTP_TLS" if tls else "FTP"
    with mock.patch.object(ftplib, cls) as ftp_cls:
        ftp = ftp_cls.return_value
        assert upload(t, archive, "shop.sql.bz2") == "ftp://ftp.local/bk/shop.sql.bz2"
    ftp.connect.assert_called_once_with("ftp.local", 2121)
    ftp.login.assert_called_once_with("u", "p")
    assert ftp.storbinary.call_args[0][0] == "STOR /bk/shop.sql.bz2"
    assert ftp.prot_p.called == tls
    ftp.quit.assert_called_once()


def test_ftp_failure_removes_partial_file(archive):
    t = FTPTarget(host="ftp.local", user="u", password="p")
    with mock.patch.object(ftplib, "FTP") as ftp_cls:
        ftp = ftp_cls.return_value
        ftp.storbinary.side_effect = ftplib.error_temp("451 disk full")
        with pytest.raises(ftplib.error_temp):
            upload(t, archive, "shop.sql.bz2")
    ftp.delete.assert_called_once_with("shop.sql.bz2")
    ftp.quit.assert_called_once()
