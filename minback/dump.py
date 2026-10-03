"""Run mariadb-dump and spool its bzip2-compressed output to a file."""

from __future__ import annotations

import bz2
import os
import shutil
import subprocess
import tempfile

from .config import Config

CHUNK = 1024 * 1024


class DumpError(RuntimeError):
    pass


def _defaults_file(cfg: Config, tmp_dir: str) -> str:
    # Pass credentials via an option file so the password never shows up in `ps`.
    fd, path = tempfile.mkstemp(prefix="minback-", suffix=".cnf", dir=tmp_dir)
    password = cfg.db_password.replace("\\", "\\\\").replace('"', '\\"')
    with os.fdopen(fd, "w") as f:
        f.write(f'[client]\npassword="{password}"\n')
    os.chmod(path, 0o600)
    return path


def dump(cfg: Config, dest: str, binary: str = "mariadb-dump") -> int:
    """Dump cfg.db compressed into dest. Returns the compressed size in bytes."""
    cnf = _defaults_file(cfg, os.path.dirname(dest) or cfg.tmp_dir)
    try:
        cmd = [
            binary,
            f"--defaults-extra-file={cnf}",
            "--single-transaction",
            f"--host={cfg.db_host}",
            f"--port={cfg.db_port}",
            f"--user={cfg.db_user}",
            cfg.db,
        ]
        # stderr goes to a file so a chatty dump can't block on a full pipe.
        with (
            open(dest, "wb") as raw,
            bz2.BZ2File(raw, "wb") as out,
            tempfile.TemporaryFile(dir=cfg.tmp_dir) as err,
        ):
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err)
            try:
                shutil.copyfileobj(proc.stdout, out, CHUNK)
            finally:
                proc.stdout.close()
                rc = proc.wait()
            err.seek(0)
            stderr = err.read().decode(errors="replace").strip()
        if rc != 0:
            raise DumpError(f"mariadb-dump exited with {rc}: {stderr}")
        return os.path.getsize(dest)
    finally:
        os.unlink(cnf)
