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


RULENAMES: Tuple[str] = ("second", "minute", "hour", "day", "month")
