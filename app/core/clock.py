"""Single source of "now". Tests monkeypatch `utcnow` to control time."""

from datetime import UTC, date, datetime, timedelta, timezone

# Asia/Seoul has had no DST since 1988; a fixed offset avoids needing tzdata on Windows.
KST = timezone(timedelta(hours=9), "KST")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def now() -> datetime:
    """Timezone-aware current time (UTC). Never use naive datetime.now()."""
    return utcnow()


def today_kst() -> date:
    return now().astimezone(KST).date()
