import json
import time

from aredis import StrictRedis

from ..rule import Rule
from . import BaseBackend

SLIDING_WINDOW_SCRIPT = """
-- Set variables from arguments
local now = tonumber(ARGV[1])
local ruleset = cjson.decode(ARGV[2])
-- ruleset looks like this:
-- {key: [limit, window_size], ...}
local scores = {}
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
end
return scores
"""

WINDOW_SIZE = {
    "second": 1,
    "minute": 60,
    "hour": 60 * 60,
    "day": 24 * 60 * 60,
    "month": 31 * 24 * 60 * 60,
}


class SlidingRedisBackend(BaseBackend):
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
        ruleset = rule.ruleset(path, user, WINDOW_SIZE)
        keys = list(ruleset.keys())
        args = [(epoch), json.dumps(ruleset)]
        argss = [f"'{a}'" for a in args]
        cli = f"redis-cli --ldb --eval /tmp/script.lua {' '.join(keys)} , {' '.join(argss)}"
        print(cli)
        r = await self.sliding_function.execute(keys=keys, args=args)
        print(f"{epoch} {r} : {all(r)}")
        return all(r)

    async def decrease_limit(self, path: str, user: str, rule: Rule) -> bool:
        raise NotImplementedError()

    async def increase_limit(self, path: str, user: str, rule: Rule) -> bool:
        raise NotImplementedError()

    async def set_block_time(self, user: str, block_time: int) -> None:
        await self._redis.set(f"blocking:{user}", True, block_time)

    async def is_blocking(self, user: str) -> bool:
        return bool(await self._redis.get(f"blocking:{user}"))

    async def allow_request(self, path: str, user: str, rule: Rule) -> bool:
        if await self.is_blocking(user):
            return False

        allow = await self.get_limits(path, user, rule)

        if not allow and rule.block_time:
            await self.set_block_time(user, rule.block_time)

        return allow
