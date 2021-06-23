import json
import time

from aredis import StrictRedis

from ..rule import Rule
from . import BaseBackend

SLIDING_WINDOW_SCRIPT = """
-- Set variables from arguments
local now = tonumber(ARGV[1])
local ruleset = cjson.decode(ARGV[2])
local result = {}
-- ruleset looks like this:
-- {key: [limit, window_size], ...}
local scores = {}
local min = {}
local expire_in = {}
for i, pgname in ipairs(KEYS) do
    -- we remove keys older than now - window_size
    local clearBefore = now - ruleset[pgname][2]
    redis.call('ZREMRANGEBYSCORE', pgname, 0, clearBefore)
    -- we get the count
    local amount = redis.call('ZCARD', pgname)
    -- we add to sorted set if allowed ie the amount < limit
    if amount < ruleset[pgname][1] then
        redis.call('ZADD', pgname, now, now)
    end
    -- cleanup, this expires the whole set in window_size secs
    redis.call('EXPIRE', pgname, ruleset[pgname][2])
    -- calculate the remaining amount of requests. If >= 0 then request for that window is allowed
    scores[i] = ruleset[pgname][1] - amount
    min[i] = redis.call('ZRANGE', pgname, 0, 0)[1]
    expire_in[i] = - now + tonumber(min[i]) + ruleset[pgname][2]
end
result['scores'] = scores
result['expire_in'] = expire_in
return cjson.encode(result)
"""


class SlidingRedisBackend(BaseBackend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = None,
        ssl: bool = False,
    ) -> None:
        self._redis = StrictRedis(
            host=host, port=port, db=db, password=password, ssl=ssl
        )
        self.sliding_function = self._redis.register_script(SLIDING_WINDOW_SCRIPT)

    async def get_limits(self, path: str, user: str, rule: Rule) -> dict:
        epoch = time.time()
        ruleset = rule.ruleset(path, user)
        r = await self.sliding_function.execute(
            keys=list(ruleset.keys()), args=[epoch, json.dumps(ruleset)]
        )
        mr = json.loads(r.decode())
        # we need that in case redis returns no values for a given key, "scores" or "expire_in"
        # if that is the case the corresponding value will be {} and we transform it to []
        mr = {k: (v if v != {} else []) for k, v in mr.items()}
        mr["epoch"] = epoch
        return mr

    async def set_block_time(self, user: str, block_time: int) -> None:
        await self._redis.set(f"blocking:{user}", True, block_time)

    async def is_blocking(self, user: str) -> int:
        return int(await self._redis.ttl(f"blocking:{user}"))

    async def retry_after(self, path: str, user: str, rule: Rule) -> int:
        block_time = await self.is_blocking(user)
        if block_time > 0:
            return block_time

        limits = await self.get_limits(path, user, rule)
        retry_after = limits["expire_in"][0] if not all(limits["scores"]) else 0

        if retry_after > 0 and rule.block_time:
            await self.set_block_time(user, rule.block_time)
            retry_after = rule.block_time

        return round(retry_after)
