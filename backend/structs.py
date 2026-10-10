"""Structs"""

from datetime import datetime

from pydantic import BaseModel, Field


class Relay(BaseModel):
    """Relay Structs"""

    nickname: str
    fingerprint: str
    running: bool
    measured: bool
    asn: str = Field(alias="as")
    as_name: str = ""
    consensus_weight: int
    # Onionoo 還沒處理到描述檔的中繼（多半是幾小時內剛加入的）沒有 platform 與四個頻寬欄位，
    # 有些已經是 Running。缺的時候存成 NULL，不要整批驗證失敗。
    platform: str | None = None
    version: str
    contact: str = ""
    country: str
    country_name: str
    flags: list[str]
    first_seen: datetime
    last_seen: datetime
    last_changed: datetime = Field(alias="last_changed_address_or_port")
    bandwidth_rate: int | None = None
    bandwidth_burst: int | None = None
    observed_bandwidth: int | None = None
    advertised_bandwidth: int | None = None
    guard_probability: float = 0
    middle_probability: float = 0
    exit_probability: float = 0


class Details(BaseModel):
    """Details Structs"""

    version: str
    build_revision: str
    relays_published: datetime
    bridges_published: datetime
    relays: list[Relay]
