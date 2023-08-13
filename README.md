# minback-mariadb
**Minio Backup container for MariaDB**

> [!NOTE]
> Inspired by [gh/SierraSoftworks/minback-mysql](https://github.com/SierraSoftworks/minback-mysql).

This container provides a trivially simple means to run `mariadb-dump` and fire the results off
to a Minio instance.

## Features
* Dumps a single MariaDB database to an S3 bucket
* Lightweight and short lived
* Simple and readable implementation
* Compression and ARM64 and AMD64 Docker Images

## Example
```sh
docker run --rm --env-file backup.env ghcr.io/resmo/minback-mariadb:main
```

#### `backup.env`
```
DB=my-db-table
DB_HOST=localhost
DB_PORT=3306
DB_USER=db-user
DB_PASSWORD=db-password

MINIO_SERVER=https://play.minio.io/
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=miniosecret
MINIO_BUCKET=backups
```
## Configuration

This container is configured using environment variables.

#### `DB=my-db-table`
Database name to backup (required).

#### `DB_HOST=localhost`
Database server host. Default `localhost`.

#### `DB_PORT=3306`
TCP port the server listens to. Default `3306`.

#### `DB_USER=root`
User to be used to authenticate to the server. Default `root`.

#### `DB_PASSWORD`
Password to be used to authenticate to the server (required).

#### `MINIO_SERVER=https://play.minio.io/`
The Minio server you wish to send backups to (required).

#### `MINIO_ACCESS_KEY=minio`
The Access Key used to connect to your Minio server (required).

#### `MINIO_SECRET_KEY=miniosecret`
The Secret Key used to connect to your Minio server (required).

#### `MINIO_BUCKET=backups`
The Minio bucket you wish to store your backup in (required).

#### `DATE_FORMAT=+%Y-%m-%d-%H%M`
The date format you would like to use when naming your backup files. Files are named `$DATE_FORMAT.sql.bz2`.
