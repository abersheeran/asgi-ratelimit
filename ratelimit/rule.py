from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class Rule:
    group: str = "default"

    second: Optional[int] = None
    minute: Optional[int] = None
    hour: Optional[int] = None
    day: Optional[int] = None
    month: Optional[int] = None

    block_time: Optional[int] = None

    zone: Optional[str] = None

    def ruleset(self, path: str, user: str) -> Dict[str, Tuple[int, int]]:
        """
        builds a dictionary of keys, values where keys are
        the redis keys and values is a tuple of (limit, ttl)
        """
        return {
            f"{path}:{user}:{name}": (limit, TTL[name])
            for name, limit in map(lambda name: (name, getattr(self, name)), RULENAMES)
            if limit is not None
        }


TTL = {
    "second": 1,
    "minute": 60,
    "hour": 60 * 60,
    "day": 24 * 60 * 60,
    "month": 31 * 24 * 60 * 60,
}

RULENAMES: Tuple[str, ...] = ("second", "minute", "hour", "day", "month")
