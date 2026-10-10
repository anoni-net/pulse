#!/usr/bin/env python3
"""Pulse 收集中斷的提醒。

2026-07-08 到 08-23 收集器停了 47 天，API 與資料庫一直是健康的，readyz 也是綠燈，
到整理季報時才發現。這支腳本每小時讀一次 /api/freshness，有國家的最新快照太舊、
或 API 沒有回應時推播到 ntfy。

只在狀態改變時推播：開始中斷推一次、哪些國家中斷有變化推一次、恢復再推一次，
不會每小時重複。上一次的狀態記在 PULSE_FRESHNESS_STATE。

只用標準函式庫，部署主機上用系統的 python3 執行，不必進容器。

    PULSE_NTFY=http://<ntfy 主機>/<topic> python3 tools/freshness_warn.py

環境變數：
    PULSE_NTFY              ntfy 的 topic 網址，必填
    PULSE_API               預設 http://127.0.0.1:8899/api（m6 上 api 容器對外的位址）
    PULSE_STALE_HOURS       最新快照超過幾小時算中斷，預設 4
    PULSE_FRESHNESS_STATE   預設 ~/.cache/pulse-freshness.state
    --force                 不管狀態有沒有變都推播一次，用來測試通知
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("PULSE_API", "http://127.0.0.1:8899/api").rstrip("/")
NTFY = os.environ.get("PULSE_NTFY", "")
HOURS = int(os.environ.get("PULSE_STALE_HOURS", "4"))
STATE = Path(os.environ.get("PULSE_FRESHNESS_STATE",
                            Path.home() / ".cache" / "pulse-freshness.state"))


def check() -> tuple[str, str]:
    """回傳（狀態，內文）。狀態是 ok、api-down，或中斷國家代碼用逗號接起來。"""
    try:
        with urllib.request.urlopen(f"{API}/freshness?hours={HOURS}", timeout=30) as resp:
            data = json.load(resp)
    except Exception as err:  # 連不上、503、逾時都算 API 沒有回應
        return "api-down", (f"{API}/freshness 沒有回應：{err}\n\n"
                            "先看 docker compose ps 與 api 的 log。")
    if not data["stale"]:
        return "ok", "所有國家的最新快照都在 {} 小時內。".format(HOURS)
    lines = []
    for c in data["countries"]:
        if c["stale"]:
            if c["age_hours"] is None:
                age = "八天內沒有資料"
            else:
                age = f"最新快照 {c['latest'][:16]}，{c['age_hours']} 小時前"
            lines.append(f"- {c['country']}：{age}")
    if len(data["stale"]) == len(data["countries"]):
        hint = ("全部國家都中斷，多半是收集器停了："
                "docker compose ps、docker compose logs --tail 50 backend。")
    else:
        hint = "只有部分國家中斷，可能是那些國家的中繼都離開了，先查 Onionoo 再看 backend 的 log。"
    body = "\n".join(lines) + "\n\n" + hint
    return ",".join(data["stale"]), body


def notify(title: str, body: str, priority: str, tags: str) -> None:
    # 標題有中文，HTTP 標頭只能放 latin-1，改用 ntfy 的查詢參數
    query = urllib.parse.urlencode({"title": title, "priority": priority, "tags": tags})
    req = urllib.request.Request(f"{NTFY}?{query}", data=body.encode(), method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def main() -> int:
    if not NTFY:
        print("PULSE_NTFY 沒有設定", file=sys.stderr)
        return 2
    force = "--force" in sys.argv[1:]
    state, body = check()
    previous = STATE.read_text().strip() if STATE.exists() else "ok"
    if state == previous and not force:
        print(f"pulse freshness: {state}（沒有變化，不推播）")
        return 0
    if state == "ok":
        title, priority, tags = "Pulse 收集已恢復", "default", "white_check_mark"
    elif state == "api-down":
        title, priority, tags = "Pulse API 沒有回應", "high", "warning"
    else:
        title, priority, tags = f"Pulse 收集中斷：{state}", "high", "warning"
    try:
        notify(title, body, priority, tags)
    except Exception as err:
        # 推播失敗就不更新狀態，下一個小時再試
        print(f"pulse freshness: {state}，推播失敗：{err}", file=sys.stderr)
        return 1
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(state + "\n")
    print(f"pulse freshness: {previous} → {state}，已推播")
    return 0


if __name__ == "__main__":
    sys.exit(main())
