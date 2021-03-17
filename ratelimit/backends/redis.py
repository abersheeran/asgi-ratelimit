import time

from aredis import StrictRedis
from aredis.pipeline import StrictPipeline, WatchError

from ..rule import Rule, RULENAMES
from . import BaseBackend

SLIDING_WINDOW_SCRIPT = """
local pgname = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clearBefore = now - window

redis.call('ZREMRANGEBYSCORE', pgname, 0, clearBefore)
local amount = redis.call('ZCARD', pgname)
if amount < limit then
    redis.call('ZADD', pgname, now, now)
end
redis.call('EXPIRE', pgname, window)

return limit - amount
"""

WINDOW_SIZE = {
    "second": 1,
    "minute": 60,
    "hour": 60*60,
    "day": 24*60*60,
    "month": 31*24*60*60
}


class RedisBackend(BaseBackend):
    def __init__(
            self,
            host: str = "localhost",
            port: int = 6379,
            db: int = 0,
            password: str = None,
    ) -> None:
        self._redis = StrictRedis(host=host, port=port, db=db, password=password)
        self.sliding_function = self._redis.register_script(SLIDING_WINDOW_SCRIPT)

    async def get_limits(self, path: str, user: str, rule: Rule) -> bool:
        epoch = time.time()
        scores = []
        for name in RULENAMES:
            limit = getattr(rule, name)
            if limit is not None:
                key = f"{path}:{user}:{name}"
                print(f"limit: {limit} key: {key}")
                r = await self.sliding_function.execute(
                    keys=[key],
                    args=[epoch, WINDOW_SIZE[name], limit]
                )
                scores.append(r)
        print(f"{epoch} {scores} : {all(scores)}")
        return all(scores)

    async def decrease_limit(self, path: str, user: str, rule: Rule) -> bool:
        raise NotImplementedError()

    async def increase_limit(self, path: str, user: str, rule: Rule) -> bool:
        raise NotImplementedError()

    async def set_block_time(self, user: str, block_time: int) -> None:
        await self._redis.set(f"blocking:{user}", True, block_time)

    async def is_blocking(self, user: str) -> bool:
        return bool(await self._redis.get(f"blocking:{user}"))
