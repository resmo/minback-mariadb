from datetime import datetime

import pytest

from minback.backup import archive_name
from minback.config import Config, ConfigError, FTPTarget, S3Target


def test_defaults(env):
    cfg = Config.from_env(env)
    assert (cfg.db_host, cfg.db_port, cfg.db_user) == ("localhost", 3306, "root")
    assert cfg.retry_attempts == 3 and cfg.retry_delay == 30
    assert cfg.notify_on == "failure"
    assert cfg.listen == ("0.0.0.0", 8080)
    [s3] = cfg.targets
    assert isinstance(s3, S3Target)
    assert (s3.bucket, s3.region, s3.api_version) == ("backups", "us-east-1", "S3v4")


def test_ftp_and_s3_targets(env):
    env.update(
        {
            "FTP_HOST": "ftp",
            "FTP_USER": "u",
            "FTP_PASSWORD": "p",
            "FTP_PORT": "2121",
            "FTP_TLS": "true",
            "FTP_DIR": "/backups",
        }
    )
    cfg = Config.from_env(env)
    assert [t.name for t in cfg.targets] == ["s3", "ftp"]
    ftp = cfg.targets[1]
    assert isinstance(ftp, FTPTarget)
    assert (ftp.port, ftp.tls, ftp.directory) == (2121, True, "/backups")


def test_ftp_only(env):
    for k in ("OBJECT_SERVER", "OBJECT_ACCESS_KEY", "OBJECT_SECRET_KEY"):
        del env[k]
    env.update({"FTP_HOST": "ftp", "FTP_USER": "u", "FTP_PASSWORD": "p"})
    assert [t.name for t in Config.from_env(env).targets] == ["ftp"]


def test_old_minio_vars_are_not_read(env):
    for k in ("OBJECT_SERVER", "OBJECT_ACCESS_KEY", "OBJECT_SECRET_KEY"):
        env["MINIO_" + k.split("_", 1)[1]] = env.pop(k)
    with pytest.raises(ConfigError, match="no backup target"):
        Config.from_env(env)


@pytest.mark.parametrize(
    "remove,message",
    [
        ("DB", "DB is required"),
        ("DB_PASSWORD", "DB_PASSWORD is required"),
        ("OBJECT_SECRET_KEY", "OBJECT_SECRET_KEY required"),
    ],
)
def test_validation(env, remove, message):
    del env[remove]
    with pytest.raises(ConfigError, match=message):
        Config.from_env(env)


def test_partial_ftp_config(env):
    env["FTP_HOST"] = "ftp"
    with pytest.raises(ConfigError, match="FTP_USER, FTP_PASSWORD required"):
        Config.from_env(env)


@pytest.mark.parametrize(
    "key,value",
    [
        ("NOTIFY_ON", "sometimes"),
        ("DB_PORT", "abc"),
        ("OBJECT_API_VERSION", "v9"),
    ],
)
def test_invalid_values(env, key, value):
    env[key] = value
    with pytest.raises(ConfigError, match=key):
        Config.from_env(env)


@pytest.mark.parametrize("fmt", ["+%Y-%m-%d-%H%M", "%Y-%m-%d-%H%M"])
def test_date_format_accepts_date1_syntax(env, fmt):
    env["DATE_FORMAT"] = fmt
    cfg = Config.from_env(env)
    assert archive_name(cfg, datetime(2026, 10, 3, 4, 5)) == "shop-2026-10-03-0405.sql.bz2"
