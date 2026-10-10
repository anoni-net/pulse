-- asn_count：ooni.py 匯入的 OONI 各 ASN 觀測次數。跟正式機的實際結構對齊（2026-10）。

CREATE TABLE IF NOT EXISTS asn_count (
    country varchar(10),
    created_at timestamp,
    asn varchar(10),
    times smallint NOT NULL,
    UNIQUE (country, created_at, asn)
);
