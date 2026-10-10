# AGENTS.md

本文件寫給在 Pulse repo 工作的 AI 協作工具與使用它們的貢獻者。Claude Code 從 `CLAUDE.md` 引入這一份。說明文件的寫法照 anoni.net 的[寫作風格規範](https://anoni.net/join/writing-style/)。

Pulse 在 2026-10 從 [`anoni-net/docs`](https://github.com/anoni-net/docs) 的 `pulse/` 目錄拆出來，commit 歷史一併帶過來，舊 commit 訊息裡的 PR 編號寫成 `anoni-net/docs#123`。

## 專案定位

Pulse 是 anoni.net 社群 [Tor 中繼節點觀測](https://anoni.net/projects/pulse/)背後的 Tor 中繼監控系統，定期從 Tor Onionoo API 收集 TW、HK、MO、JP、KR、SG、VN、IN、ID、MY、PH、TH、DE、NL、US 十五個國家的中繼節點資料（清單在 `backend/countries.py`），儲存至 PostgreSQL，並透過 FastAPI 提供 Vega-Lite 圖表資料端點。

## 開發指令

```bash
# 本地 API 開發（熱重載）
cd backend
uv sync
uv run fastapi dev api.py

# 手動觸發資料收集
uv run python tor.py collect                 # countries.py 的全部國家，依序一次一個
uv run python tor.py details --country=jp   # 只收一個國家

# 載入 OONI ASN 資料
uv run python ooni.py asn --path=<csv_file> --save=True

# Lint（ruff，設定於 pyproject.toml）
uv run ruff check .
uv run ruff format .

# 完整 stack（PostgreSQL + backend cron + API）
docker-compose up -d
docker-compose logs -f
```

## 架構概覽

四個 Docker 服務：

| 服務 | 職責 |
|------|------|
| **db** | PostgreSQL 18，`./data` 掛到 `/var/lib/postgresql` |
| **db-init** | 一次性執行 `dbtxt/*.sql` 建 schema |
| **backend** | Alpine crond，每小時第 5 分鐘依序收集十五個國家的資料 |
| **api** | FastAPI，port 8000 |

資料流：`Onionoo API → tor.py → relay_details 表 → vega.py 端點 → Vega-Lite 前端`

## 程式碼結構

```
backend/
├── api.py              # FastAPI 進入點，含 CORS / healthz / readyz / freshness
├── countries.py        # 收集的國家清單，收集排程與 API 共用
├── tor.py              # Click CLI，fetch → validate → upsert
├── tor_onionoo.py      # requests.Session 封裝 Onionoo API
├── ooni.py             # OONI CSV 資料匯入
├── pgdb.py             # psycopg3 context manager（PGConn）
├── structs.py          # Pydantic v2 models（Relay, Details）
├── routers/vega.py     # 5 個 Vega-Lite 圖表端點
└── dbtxt/              # SQL schema（relay_details, asn_count）
```

## 關鍵設計

**DB 操作**：使用 `with PGConn() as pg:` context manager，commit/rollback 自動處理。驅動是 psycopg3（非 psycopg2）。

**Pydantic 欄位別名**：`structs.py` 中 `Relay` 的 `asn` 對應 Onionoo 的 `as` 欄位，`last_changed` 對應 `last_changed_address_or_port`，`model_dump()` 輸出用於 SQL 插入。

**Node type 計算**：`vega.py` 中依 `guard_probability / middle_probability / exit_probability` 欄位判斷節點類型（GUARD / MIDDLE / EXIT），非從 Onionoo 直接取得。

**API 路由前綴**：`root_path="/api"`，所有端點實際路徑加 `/api`。Swagger UI 在 `GET /api/readme`。

**健康檢查分工**：`/api/healthz` 只回應用程式版本，`/api/readyz` 每次呼叫都開一條 PostgreSQL 連線，連不上回 503。compose 裡 api 的 healthcheck 探測 `readyz`。判斷「圖表沒資料」時看 `readyz`，`healthz` 綠燈只代表 process 還活著。兩支都送 `Cache-Control: no-store`，否則 CDN 會把某一刻的健康狀態存起來，監控讀到的是過期答案。

**快取兩層**：`vega.py` 的 `TTLCache` 是行程內快取，`cache_headers` 依賴項讓五個圖表端點都送 `Cache-Control: public, max-age=300`，兩者共用 `CACHE_TTL_SECONDS`。沒有這個 header 時 CDN 會套用 zone 預設值（anoni.net 是 4 小時），收集器每小時寫一次，edge 上那份會讓圖表在資料恢復後繼續顯示舊值好幾個小時。查「資料是不是真的沒更新」時先繞過 CDN 打 origin，或加一個隨機查詢參數。

**Vega 端點**：共 5 個，均接受 `country`（`routers/vega.py` 的 `Country` enum，由 `countries.py` 產生，跟收集的國家相同）和 `limit=45` 參數，回傳 Pydantic model 的 JSON 陣列。

**uv 來源**：兩個 Dockerfile 都用 `COPY --from=ghcr.io/astral-sh/uv:<版本> /uv /uvx /bin/` 取得 uv，build 期間不連 astral.sh。改回 `curl | sh` 會讓網路失敗變成難查的 `exit code 127`，因為 pipeline 的 exit code 取自 `sh`，curl 的失敗被吞掉，一路走到 `uv sync` 才報錯。升級 uv 就是改那個版本號。

**Cron 設定**：Dockerfile 建置時寫入 `/etc/crontabs/root`，`5 * * * *` 執行一次 `tor.py collect`，依序收集 `countries.py` 的每個國家，容器重啟時 `@reboot` 也觸發一次。一個國家失敗不影響其他國家。新增國家只改 `countries.py`，舊的快照沒有那個國家，頁面從加入那天開始畫。

**收集中斷的提醒**：`/api/freshness` 回傳每個國家最新快照的時間，超過門檻（預設 4 小時）的列在 `stale`。readyz 只看得到資料庫，收集器靜靜停掉時 API 與資料庫照樣健康，2026-07-08 到 08-23 就這樣少了 47 天。部署主機每小時用 `tools/freshness_warn.py` 讀它，狀態改變時推播到 ntfy，用法寫在腳本開頭。

## 環境設定

`.env.sample` → 複製為 `.env`，關鍵變數：

```
PG_HOST="127.0.0.1:5432"
PG_DB="..."
PG_USER="..."
PG_PASSWORD="..."
API_HOST="127.0.0.1:8000"
```

Backend 內部讀取 `PG_CONN` 連線字串（由 docker-compose 組合）。`CORS_ALLOW_ORIGINS` 為逗號分隔的允許來源清單（預設 `*`）。

## Schema 修改流程

`dbtxt/*.sql` 是全新安裝用的結構。db-init 每次啟動都會執行，但裡面全部是 `IF NOT EXISTS`，對已經存在的表不會有作用，重建 db-init 改不到既有的資料庫。改既有的資料庫要另外寫遷移：

1. 在 `dbtxt/migrations/` 新增下一個編號的 SQL，寫成可以重複執行（`IF EXISTS`、`IF NOT EXISTS`）
2. 同步改 `dbtxt/*.sql`，讓全新安裝跟遷移之後的結構一致
3. 驗證：拿正式機的 `pg_dump --schema-only` 還原到暫時的容器，套用遷移，再跟全新安裝的 `pg_dump --schema-only` 比對
4. 在部署主機上手動執行，先套遷移再部署新的程式：

    ```bash
    docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' \
      < backend/dbtxt/migrations/005_nullable_bandwidth_and_drop_serial_defaults.sql
    ```

正式機目前套用到 005（2026-10-10）。004 在這之前一直沒有套用，2026-10-10 跟 005 一起補上，`dbtxt/*.sql` 也在同一天改成跟正式機的實際結構一致：時間欄位不帶時區，帶時區的話 `date(created_at)` 建不起索引，全新安裝會在 db-init 失敗。001 用了 `CONCURRENTLY`，不能包在交易裡執行。006 新增 `consensus_weight_fraction`，部署寫入這個欄位的 backend 之前要先套用，否則每一次收集都會失敗。

正式機另外有一張 `test` 表，不在 `dbtxt/` 裡，跟 Pulse 的程式無關。

## 套件升級與部署

Dependabot 每週檢查 Python 套件、兩個 Dockerfile 的基底映像、`docker-compose.yml` 的 PostgreSQL 與 GitHub Actions，PR 由 `check` workflow 驗證。手動升級、部署步驟與 PostgreSQL 換 major 版本的搬遷（`tools/pg-major-upgrade.sh`）見 README 的「套件升級與部署」。

- FastAPI 不要改回 `fastapi[standard]`，那組選用相依會帶進 FastAPI Cloud 的 CLI、sentry 與 OpenTelemetry 的匯出套件，Pulse 用不到
- 部署前更新 `backend/api.py` 的 `version`，部署後用 `/api/healthz` 確認換上新版
