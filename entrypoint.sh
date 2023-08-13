#!/bin/bash
set -e -o pipefail

mc config host add pg "$MINIO_SERVER" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api "$MINIO_API_VERSION" > /dev/null

ARCHIVE="${MINIO_BUCKET}/${DB}-$(date "$DATE_FORMAT").archive"

echo "Dumping $DB to $ARCHIVE from $DB_HOST:$DB_PORT with user $DB_USER"

mariadb-dump "$DB" --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" --password="$DB_PASSWORD" | mc pipe "pg/$ARCHIVE" || { echo "Backup failed"; mc rm "pg/$ARCHIVE"; exit 1; }

echo "Backup complete"
