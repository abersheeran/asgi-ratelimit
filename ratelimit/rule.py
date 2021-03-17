from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Rule:
    group: str = "default"

    second: Optional[int] = None
    minute: Optional[int] = None
    hour: Optional[int] = None
    day: Optional[int] = None
    month: Optional[int] = None

    block_time: Optional[int] = None

    def ruleset(self, path, user, window_size):
        d = {}
        for name in RULENAMES:
            limit = getattr(self, name)
            if limit is not None:
                key = f"{path}:{user}:{name}"
                d[key] = (limit, window_size[name])
        return d


RULENAMES: Tuple[str] = ("second", "minute", "hour", "day", "month")
