"""
Timezone-aware IST helpers.
"""

from datetime import datetime, time

import pytz  # type: ignore

IST = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def parse_time_ist(hhmm: str) -> time:
    """Parse 'HH:MM' into a time object."""
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def is_after_or_equal(t: time, threshold: time) -> bool:
    return (t.hour, t.minute) >= (threshold.hour, threshold.minute)


def market_open(session_start: str = "09:15", session_end: str = "15:30") -> bool:
    now = now_ist().time()
    start = parse_time_ist(session_start)
    end = parse_time_ist(session_end)
    return start <= now <= end
