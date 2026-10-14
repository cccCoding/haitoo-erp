"""货盘账号有效期使用香港自然月，数据库保持 UTC 无时区时间。"""

import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


HONG_KONG = ZoneInfo("Asia/Hong_Kong")


def as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def add_calendar_months(value: datetime, months: int) -> datetime:
    if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
        raise ValueError("使用有效时间必须为正整数月")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(HONG_KONG)
    absolute_month = local.year * 12 + local.month - 1 + months
    year, zero_based_month = divmod(absolute_month, 12)
    month = zero_based_month + 1
    if not 1 <= year <= 9999:
        raise ValueError("使用有效时间超出支持范围")
    day = min(local.day, calendar.monthrange(year, month)[1])
    return as_utc_naive(local.replace(year=year, month=month, day=day))


def supply_user_is_expired(user, now: datetime | None = None) -> bool:
    expiry = user.supply_expires_at
    return expiry is None or as_utc_naive(expiry) <= as_utc_naive(now or datetime.now(timezone.utc))
