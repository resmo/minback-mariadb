import bz2
import stat
import textwrap

import pytest

from minback.dump import DumpError, dump


def fake_binary(tmp_path, body):
    path = tmp_path / "mariadb-dump"
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_dump_compresses_and_hides_password(cfg, tmp_path):
    # Echo argv and the defaults file so we can assert on them.
    binary = fake_binary(
        tmp_path,
        """
        cnf=$(echo "$1" | sed 's/--defaults-extra-file=//')
        echo "ARGS: $*"
        cat "$cnf"
        echo "-- dump of $6"
    """,
    )
    dest = tmp_path / "out.sql.bz2"
    size = dump(cfg, str(dest), binary=binary)
    assert size == dest.stat().st_size
    text = bz2.decompress(dest.read_bytes()).decode()
    assert "--single-transaction" in text
    assert "--host=localhost --port=3306 --user=root shop" in text
    assert 'password="secret"' in text
    assert "secret" not in text.splitlines()[0], "password must not be on the command line"
    assert "-- dump of shop" in text
    assert not list(tmp_path.glob("minback-*.cnf")), "defaults file must be removed"


def test_dump_failure_raises_with_stderr(cfg, tmp_path):
    binary = fake_binary(
        tmp_path,
        """
        echo "partial"
        echo "Access denied for user" >&2
        exit 2
    """,
    )
    with pytest.raises(DumpError, match="exited with 2: Access denied"):
        dump(cfg, str(tmp_path / "out.sql.bz2"), binary=binary)
    assert not list(tmp_path.glob("minback-*.cnf"))
