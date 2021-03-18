import datetime
import json
import logging
import time

from aredis import StrictRedis

from ..rule import Rule
from . import BaseBackend


# class TimeFilter(logging.Filter):
#     def filter(self, record):
#         try:
#             last = self.last
#         except AttributeError:
#             last = record.relativeCreated
#         delta = datetime.datetime.fromtimestamp(
#             record.relativeCreated / 1000.0
#         ) - datetime.datetime.fromtimestamp(last / 1000.0)
#         record.relative = "{0:.2f}".format(
#             delta.seconds + delta.microseconds / 1000000.0
#         )
#         self.last = record.relativeCreated
#         return True
#
#
# logger = logging.getLogger("ratelimit")
# logger.setLevel(logging.DEBUG)
# ch = logging.StreamHandler()
# ch.setLevel(logging.DEBUG)
# formatter = logging.Formatter(
#     fmt="+%(relative)s - %(name)s - %(levelname)s - %(message)s"
# )
# logger.addHandler(ch)
# [hndl.addFilter(TimeFilter()) for hndl in logger.handlers]
# [hndl.setFormatter(formatter) for hndl in logger.handlers]


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
        ruleset = rule.ruleset(path, user)
        keys = list(ruleset.keys())
        args = [epoch, json.dumps(ruleset)]
        # quoted_args = [f"'{a}'" for a in args]
        # cli = f"redis-cli --ldb --eval /tmp/script.lua {' '.join(keys)} , {' '.join(quoted_args)}"
        # logger.debug(cli)
        r = await self.sliding_function.execute(keys=keys, args=args)
        # logger.debug(f"{epoch} {r} : {all(r)}")
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
