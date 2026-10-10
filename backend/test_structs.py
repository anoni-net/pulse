"""structs 的解析測試。不需要資料庫，也不連 Onionoo：uv run python test_structs.py"""

from structs import Details

BASE = {
    "nickname": "example",
    "fingerprint": "0" * 40,
    "running": True,
    "measured": False,
    "as": "AS3462",
    "consensus_weight": 1,
    "version": "0.4.9.14",
    "country": "tw",
    "country_name": "Taiwan",
    "flags": ["Running", "Valid"],
    "first_seen": "2026-10-10 00:00:00",
    "last_seen": "2026-10-10 02:00:00",
    "last_changed_address_or_port": "2026-10-10 00:00:00",
}
FULL = {
    **BASE,
    "platform": "Tor 0.4.9.14 on Linux",
    "bandwidth_rate": 1073741824,
    "bandwidth_burst": 1073741824,
    "observed_bandwidth": 7174337,
    "advertised_bandwidth": 7174337,
}


def details(*relays):
    return Details.model_validate({
        "version": "8.0",
        "build_revision": "x",
        "relays_published": "2026-10-10 02:00:00",
        "bridges_published": "2026-10-10 02:00:00",
        "relays": list(relays),
    })


def test_full_relay():
    relay = details({**FULL, "consensus_weight_fraction": 1.2e-4}).relays[0]
    assert relay.platform == "Tor 0.4.9.14 on Linux"
    assert relay.observed_bandwidth == 7174337
    assert relay.consensus_weight_fraction == 1.2e-4


def test_relay_without_descriptor():
    # 2026-10 實測：剛加入的中繼在 Onionoo 還沒有 platform 與四個頻寬欄位，
    # 原本整個國家的那一批會驗證失敗。現在只有缺的欄位是 None，同一批的其他中繼照常解析。
    parsed = details(FULL, BASE).relays
    assert len(parsed) == 2
    assert parsed[1].platform is None
    assert parsed[1].bandwidth_rate is None
    assert parsed[1].observed_bandwidth is None
    assert parsed[1].running is True


if __name__ == "__main__":
    test_full_relay()
    test_relay_without_descriptor()
    print("structs 測試通過")
