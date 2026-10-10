-- Migration 005: 頻寬欄位改成可以是 NULL，拿掉誤用 serial 留下的預設值與 sequence
--
-- Onionoo 還沒處理到描述檔的中繼（多半是幾小時內剛加入的）沒有 platform 與四個頻寬欄位。
-- 原本這四欄是 NOT NULL，寫入前的驗證整批失敗，那個國家那一小時的資料全部沒收進來。
--
-- 正式機上這幾欄的預設值是 nextval(sequence)，是早期把欄位宣告成 serial 留下的，
-- 寫入時一律帶值，從來沒有用到。asn_count.times 也一樣。
--
-- 可以在線上執行，只改欄位的定義，不會重寫整張表。重複執行也安全。

ALTER TABLE relay_details
    ALTER COLUMN bandwidth_rate DROP NOT NULL,
    ALTER COLUMN bandwidth_rate DROP DEFAULT,
    ALTER COLUMN bandwidth_burst DROP NOT NULL,
    ALTER COLUMN bandwidth_burst DROP DEFAULT,
    ALTER COLUMN observed_bandwidth DROP NOT NULL,
    ALTER COLUMN observed_bandwidth DROP DEFAULT,
    ALTER COLUMN advertised_bandwidth DROP NOT NULL,
    ALTER COLUMN advertised_bandwidth DROP DEFAULT,
    ALTER COLUMN consensus_weight DROP DEFAULT;

ALTER TABLE asn_count ALTER COLUMN times DROP DEFAULT;

DROP SEQUENCE IF EXISTS
    relay_details_bandwidth_rate_seq,
    relay_details_bandwidth_burst_seq,
    relay_details_observed_bandwidth_seq,
    relay_details_advertised_bandwidth_seq,
    relay_details_consensus_weight_seq,
    asn_count_times_seq;
