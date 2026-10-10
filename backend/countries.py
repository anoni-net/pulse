"""收集的國家，Onionoo 的 country 參數用的 ISO 3166-1 兩碼小寫。

收集排程（tor.py collect）、API 的 country 參數與 /api/freshness 都讀這一份。
亞洲的地區在前，德國、荷蘭、美國是中繼最多的地區，留著當作參照。
"""

COUNTRIES = (
    "tw", "hk", "mo", "jp", "kr", "sg", "vn", "in",
    "id", "my", "ph", "th",
    "de", "nl", "us",
)
