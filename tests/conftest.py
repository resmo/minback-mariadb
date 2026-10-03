import pytest

from minback.config import Config

BASE_ENV = {
    "DB": "shop",
    "DB_PASSWORD": "secret",
    "OBJECT_SERVER": "http://s3.local:9000",
    "OBJECT_ACCESS_KEY": "ak",
    "OBJECT_SECRET_KEY": "sk",
}


@pytest.fixture
def env():
    return dict(BASE_ENV)


@pytest.fixture
def cfg(env, tmp_path):
    env.update(
        {
            "FTP_HOST": "ftp.local",
            "FTP_USER": "u",
            "FTP_PASSWORD": "p",
            "RETRY_ATTEMPTS": "3",
            "RETRY_DELAY": "1",
            "BACKUP_TMP_DIR": str(tmp_path),
        }
    )
    return Config.from_env(env)
