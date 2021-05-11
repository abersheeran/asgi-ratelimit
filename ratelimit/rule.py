from dataclasses import dataclass
from typing import List, Optional, Tuple

WINDOW_SIZE = {
    "second": 1,
    "minute": 60,
    "hour": 60 * 60,
    "day": 24 * 60 * 60,
    "month": 31 * 24 * 60 * 60,
}


@dataclass
class LimitFrequency:
    limit: int
    granularity: int


@dataclass
class CustomRule:
    group: str = "default"
    rules: List[LimitFrequency] = None

    def ruleset(self, path, user):
        d = {}
        for cr in self.rules:
            key = f"{path}:{user}:{cr.limit}/{cr.granularity}"
            d[key] = (cr.limit, cr.granularity)
        return d

    block_time: Optional[int] = None


@dataclass
class FixedRule:
    group: str = "default"

    second: Optional[int] = None
    minute: Optional[int] = None
    hour: Optional[int] = None
    day: Optional[int] = None
    month: Optional[int] = None

    block_time: Optional[int] = None

    def ruleset(self, path, user):
        """
        builds a dictionnary of keys, values where keys are the redis keys, and values
        is a tuple of (limit, window_size)
        """
        d = {}
        for name in RULENAMES:
            limit = getattr(self, name)
            if limit is not None:
                key = f"{path}:{user}:{name}"
                d[key] = (limit, WINDOW_SIZE[name])
        return d


RULENAMES: Tuple[str] = ("second", "minute", "hour", "day", "month")
