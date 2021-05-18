import json
import time
from typing import List, Tuple, TypedDict, Union

from aredis import StrictRedis

from ..rule import FixedRule
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


class RedisResult(TypedDict):
    scores: List[int]
    expire_in: List[Union[float, int]]
    epoch: float


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

    async def get_limits(self, path: str, user: str, rule: FixedRule) -> RedisResult:
        epoch = time.time()
        ruleset = rule.ruleset(path, user)
        keys = list(ruleset.keys())
        args = [epoch, json.dumps(ruleset)]
        from tests.backends.test_redis import logger

        # quoted_args = [f"'{a}'" for a in args]
        # cli = f"redis-cli --ldb --eval /tmp/script.lua {' '.join(keys)} , {' '.join(quoted_args)}"
        # logger.debug(cli)
        r = await self.sliding_function.execute(keys=keys, args=args)
        mr = json.loads(r.decode())
        # we need that in case redis returns no values for a given key, "scores" or "expire_in"
        # if that is the case the corresponding value will be {} and we transform it to []
        mr = {k: (v if v != {} else []) for k, v in mr.items()}
        mr["epoch"] = epoch
        logger.debug("\n")
        logger.debug(mr)
        # logger.debug(f"{epoch} {mr['scores']}:{all(r)}")
        return mr

    async def decrease_limit(self, path: str, user: str, rule: FixedRule) -> bool:
        raise NotImplementedError()

    async def increase_limit(self, path: str, user: str, rule: FixedRule) -> bool:
        raise NotImplementedError()

    async def set_block_time(self, user: str, block_time: int) -> None:
        await self._redis.set(f"blocking:{user}", True, block_time)

    async def is_blocking(self, user: str) -> bool:
        return bool(await self._redis.get(f"blocking:{user}"))

    async def allow_request(
        self, path: str, user: str, rule: FixedRule
    ) -> Tuple[bool, RedisResult]:
        if await self.is_blocking(user):
            return False, {
                "expire_in": [rule.block_time],
                "scores": None,
                "epoch": time.time(),
            }

        limits = await self.get_limits(path, user, rule)
        allow = all(limits["scores"])

        if not allow and rule.block_time:
            await self.set_block_time(user, rule.block_time)

        return allow, limits
