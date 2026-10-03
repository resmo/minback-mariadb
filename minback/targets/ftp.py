"""FTP / explicit FTPS."""

from __future__ import annotations

import ftplib
import logging
import posixpath

from ..config import FTPTarget

log = logging.getLogger(__name__)
TIMEOUT = 60


def connect(t: FTPTarget) -> ftplib.FTP:
    ftp = ftplib.FTP_TLS(timeout=TIMEOUT) if t.tls else ftplib.FTP(timeout=TIMEOUT)
    ftp.connect(t.host, t.port)
    ftp.login(t.user, t.password)
    if t.tls:
        ftp.prot_p()
    return ftp


def upload(t: FTPTarget, path: str, name: str) -> str:
    remote = posixpath.join(t.directory, name) if t.directory else name
    ftp = connect(t)
    try:
        with open(path, "rb") as f:
            try:
                ftp.storbinary(f"STOR {remote}", f)
            except Exception:
                try:
                    ftp.delete(remote)
                except ftplib.all_errors as e:
                    log.warning("could not remove partial upload %s: %s", remote, e)
                raise
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()
    return f"ftp://{t.host}/{remote.lstrip('/')}"
