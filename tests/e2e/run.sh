#!/bin/bash
# End-to-end test: real MariaDB, S3 (RustFS), FTP server and webhook receiver.
# Usage: tests/e2e/run.sh   (DOCKER=podman COMPOSE=podman-compose to override)
set -euo pipefail

cd "$(dirname "$0")"
DOCKER=${DOCKER:-docker}
COMPOSE=${COMPOSE:-$DOCKER compose}
c() { $COMPOSE -p minback-e2e -f compose.yml "$@"; }
py() { c run --rm --no-deps -T --entrypoint /opt/venv/bin/python minback "$@"; }
step() { echo; echo "=== $*"; }

cleanup() { c down -v >/dev/null 2>&1 || true; }
trap cleanup EXIT

step "Build image"
$DOCKER build -q -t minback-mariadb:dev ../.. >/dev/null

step "Start services"
c up -d mariadb s3 ftp webhook
for _ in $(seq 60); do
    c exec -T mariadb mariadb -uroot -prootpw -e "SELECT 1 FROM shop.products LIMIT 1" >/dev/null 2>&1 && break
    sleep 1
done
for _ in $(seq 30); do py - create-bucket < verify.py 2>/dev/null && break; sleep 1; done

step "One-shot backup succeeds"
c run --rm --no-deps minback run
py - < verify.py

step "Failure path: FTP rejects login -> retries, exit 1, webhook, S3 still uploaded"
set +e; c run --rm --no-deps -e FTP_PASSWORD=wrong minback run; rc=$?; set -e
[ "$rc" = 1 ] || { echo "expected exit 1, got $rc"; exit 1; }
c logs webhook | grep -q '"status": "failure"' || { echo "no failure webhook"; exit 1; }
echo "exit code 1 and failure webhook received"

step "Serve mode: trigger via API, check status and metrics"
c up -d minback
base=http://127.0.0.1:18080
for _ in $(seq 30); do curl -fs "$base/healthz" >/dev/null && break; sleep 1; done
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$base/backup")" = 401 ]
curl -fs -X POST -H "Authorization: Bearer t0ken" "$base/backup"
for _ in $(seq 60); do
    curl -fs "$base/status" | grep -q '"running": false' && curl -fs "$base/status" | grep -q '"last_run": "' && break
    sleep 1
done
curl -fs "$base/status"
curl -fs "$base/metrics" | grep -E '^minback_' | grep -v '_created'
curl -fs "$base/metrics" | grep -q 'minback_backup_runs_total{db="shop",status="success"} 1.0'
out=$(py - < verify.py); echo "$out"
grep -q 'COUNTS s3=3 ftp=2' <<<"$out"

step "E2E OK"
