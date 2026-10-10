-- relay_details：每小時一份 Onionoo details 的快照，一個中繼一列。
-- 跟正式機的實際結構對齊（2026-10，migrations 001 到 005 之後）。時間欄位不帶時區，
-- Onionoo 的時間本來就是 UTC；帶時區的話 date(created_at) 不是 IMMUTABLE，建不起索引。

CREATE TABLE IF NOT EXISTS relay_details (
    created_at timestamp,
    fingerprint varchar(40),
    nickname text,
    running boolean,
    measured boolean,
    asn varchar(10),
    as_name text,
    consensus_weight integer NOT NULL,
    platform text,
    version text,
    country varchar(10),
    country_name text,
    contact text,
    flags varchar(20)[],
    first_seen timestamp,
    last_seen timestamp,
    last_changed timestamp,
    -- Onionoo 還沒處理到描述檔的中繼沒有 platform 與這四個頻寬欄位，存成 NULL
    bandwidth_rate bigint,
    bandwidth_burst bigint,
    observed_bandwidth bigint,
    advertised_bandwidth bigint,
    guard_probability NUMERIC(7, 6),
    middle_probability NUMERIC(7, 6),
    exit_probability NUMERIC(7, 6),
    UNIQUE (created_at, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_relay_details_country_created
    ON relay_details (country, date(created_at) DESC);
CREATE INDEX IF NOT EXISTS idx_rd_country_running
    ON relay_details (created_at, country, running);
CREATE INDEX IF NOT EXISTS idx_rd_country_running_2
    ON relay_details (country, running);
CREATE INDEX IF NOT EXISTS idx_rd_created_fingerprint_running
    ON relay_details (created_at, fingerprint, running);
