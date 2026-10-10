#!/usr/bin/env bash
# Pulse 的 PostgreSQL 換 major 版本：匯出舊版、還原進新版的資料目錄、比對筆數。
# 在 repo 目錄執行，舊版的 compose 還在跑。這支腳本不停 api，也不切換，
# 切換（down、換資料目錄、拉新程式、up）由人在確認筆數之後手動做。
#
#   COMPOSE_PROJECT=pulse NEW_PG=postgres:18.6-alpine3.24 bash tools/pg-major-upgrade.sh
set -euo pipefail

P=${COMPOSE_PROJECT:-pulse}
NEW_PG=${NEW_PG:-postgres:18.6-alpine3.24}
STAMP=$(date +%Y%m%d-%H%M)
DUMP=pulse-$STAMP.dump
TMP=$P-pg-restore

set -a; . ./.env; set +a
mkdir -p backup
[ -e data-new ] && { echo "data-new 已經存在，先確認再刪"; exit 1; }

echo "== 1. 停 backend，凍結寫入（api 繼續服務）"
docker compose -p "$P" stop backend

echo "== 2. 用新版的 pg_dump 匯出 $DUMP"
docker run --rm --network "${P}_default" -v "$PWD/backup:/backup" \
  -e PGPASSWORD="$PG_PASSWORD" "$NEW_PG" \
  pg_dump -h db -U "$PG_USER" -d "$PG_DB" -Fc -f "/backup/$DUMP"
ls -la "backup/$DUMP"

echo "== 3. 啟動暫時的新版資料庫，還原到 data-new"
mkdir data-new
docker run -d --name "$TMP" \
  -e POSTGRES_DB="$PG_DB" -e POSTGRES_USER="$PG_USER" -e POSTGRES_PASSWORD="$PG_PASSWORD" \
  -v "$PWD/data-new:/var/lib/postgresql" -v "$PWD/backup:/backup:ro" "$NEW_PG" >/dev/null
for i in $(seq 1 60); do
  docker exec "$TMP" pg_isready -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1 && break
  sleep 2
done
# 初始化完成之前 pg_isready 也可能先回成功，多等一下讓 entrypoint 跑完重啟
sleep 5
docker exec "$TMP" pg_isready -U "$PG_USER" -d "$PG_DB"
docker exec "$TMP" pg_restore -U "$PG_USER" -d "$PG_DB" -j 4 --exit-on-error "/backup/$DUMP"
docker exec "$TMP" psql -U "$PG_USER" -d "$PG_DB" -qc "ANALYZE"

echo "== 4. 比對筆數"
q="select 'relay_details', count(*), max(created_at) from relay_details union all select 'asn_count', count(*), max(created_at) from asn_count"
old=$(docker compose -p "$P" exec -T db psql -U "$PG_USER" -d "$PG_DB" -tAc "$q")
new=$(docker exec "$TMP" psql -U "$PG_USER" -d "$PG_DB" -tAc "$q")
echo "舊：$old"
echo "新：$new"
docker exec "$TMP" psql -U "$PG_USER" -d "$PG_DB" -tAc "select version()"
docker stop "$TMP" >/dev/null && docker rm "$TMP" >/dev/null
[ "$old" = "$new" ] && echo "筆數一致，可以切換" || { echo "筆數不一致，不要切換"; exit 1; }
