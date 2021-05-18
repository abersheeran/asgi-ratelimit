import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..rule import FixedRule

if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import TypedDict
else:
    from typing_extensions import TypedDict  # pragma: no cover


class RedisResult(TypedDict):
    scores: List[int]
    expire_in: List[int]
    epoch: float


class BaseBackend(ABC):
    """
    Base class for all backend
    """

    @staticmethod
    def calc_incr_value(
        last_timestamps: List[Optional[float]], rule: FixedRule
    ) -> Dict[str, Dict[str, int]]:

        now_timestamp = time.time()
        now = datetime.utcfromtimestamp(now_timestamp)

        incr_dict: Dict[str, Dict[str, int]] = {}

        if rule.second is not None:
            if last_timestamps[0] is None or last_timestamps[0] <= now_timestamp - 1:
                incr_dict["second"] = {"value": rule.second - 1, "ttl": 1 + 1}

        if rule.minute is not None:
            if last_timestamps[1] is None or datetime.utcfromtimestamp(
                last_timestamps[1]
            ) <= now - timedelta(minutes=1):
                incr_dict["minute"] = {"value": rule.minute - 1, "ttl": 60 + 1}

        if rule.hour is not None:
            if last_timestamps[2] is None or datetime.utcfromtimestamp(  # pragma: no cover
                last_timestamps[2]
            ) <= now - timedelta(hours=1):
                incr_dict["hour"] = {"value": rule.hour - 1, "ttl": 60 * 60 + 1}

        if rule.day is not None:
            if last_timestamps[3] is None or datetime.utcfromtimestamp(  # pragma: no cover
                last_timestamps[3]
            ) <= now - timedelta(days=1):
                incr_dict["day"] = {"value": rule.day - 1, "ttl": 60 * 60 * 24 + 1}

        if rule.month is not None:
            if last_timestamps[4] is None:
                incr_dict["month"] = {
                    "value": rule.month - 1,
                    "ttl": 60 * 60 * 24 * 31 + 1,
                }
            else:
                _last_time = datetime.utcfromtimestamp(last_timestamps[4])
                if _last_time.year < now.year or _last_time.month < now.month:  # pragma: no cover
                    incr_dict["month"] = {
                        "value": rule.month - 1,
                        "ttl": 60 * 60 * 24 * 31 + 1,
                    }

        return incr_dict

    @abstractmethod
    async def decrease_limit(self, path: str, user: str, rule: FixedRule) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def increase_limit(self, path: str, user: str, rule: FixedRule) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def set_block_time(self, user: str, block_time: int) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def is_blocking(self, user: str) -> bool:
        raise NotImplementedError()

    async def allow_request(
        self, path: str, user: str, rule: FixedRule
    ) -> Tuple[bool, Optional[RedisResult]]:
        if await self.is_blocking(user):
            return False, None

        updated = await self.increase_limit(path, user, rule)
        allow = updated or await self.decrease_limit(path, user, rule)

        if not allow and rule.block_time:
            await self.set_block_time(user, rule.block_time)

        return allow, None
