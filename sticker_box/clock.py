from datetime import datetime, timedelta, timezone

FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(moment: datetime | None = None) -> str:
    return (moment or now()).strftime(FORMAT)


def parse(text: str) -> datetime:
    return datetime.strptime(text, FORMAT).replace(tzinfo=timezone.utc)


def later(minutes: int, moment: datetime | None = None) -> str:
    return stamp((moment or now()) + timedelta(minutes=minutes))
