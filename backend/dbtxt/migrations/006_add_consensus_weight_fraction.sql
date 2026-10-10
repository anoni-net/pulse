-- Migration 006: 新增 consensus_weight_fraction，中繼占全網路共識權重的比例
--
-- 中繼數量相同的兩個國家，頻寬可能差上十倍，只比數量看不出實際貢獻多少轉送能量。
-- Onionoo 的 details 直接給這個比例（0 到 1），加總起來就是一個國家占整個 Tor 網路的份額。
-- consensus_weight 本身是相對值，沒有全網路的總和就換算不出比例，所以另外存一欄。
--
-- 舊資料是 NULL，只有套用之後收集的快照才有值。新增可以是 NULL、沒有預設值的欄位，
-- PostgreSQL 只改目錄、不重寫整張表，可以在線上執行，重複執行也安全。
-- 要先套用這一份，再部署新版的 backend，否則寫入時會找不到欄位。

ALTER TABLE relay_details ADD COLUMN IF NOT EXISTS consensus_weight_fraction double precision;
