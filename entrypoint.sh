#!/bin/bash
set -e -o pipefail

echo "Start backup run"

mc config host add pg "$MINIO_SERVER" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api "$MINIO_API_VERSION" > /dev/null

ARCHIVE="${MINIO_BUCKET}/${DB}-$(date "$DATE_FORMAT").sql.bz2"

echo "Dumping $DB to $ARCHIVE from $DB_HOST:$DB_PORT with user $DB_USER"

mariadb-dump "$DB" --single-transaction --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --password="$DB_PASSWORD" | bzip2 | mc pipe "pg/$ARCHIVE" || { echo "Backup failed"; mc rm "pg/$ARCHIVE"; exit 1; }

echo ""
echo "Backup complete"
