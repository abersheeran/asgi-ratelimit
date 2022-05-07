import json

from redis.asyncio import StrictRedis
from redis.commands.core import Script

from ..rule import Rule
from . import BaseBackend

SCRIPT = """
local ruleset = cjson.decode(ARGV[1])

-- Set limits
for i, key in pairs(KEYS) do
    redis.call('SET', key, ruleset[key][1], 'EX', ruleset[key][2], 'NX')
end

-- Check limits
for i = 1, #KEYS do
    local value = redis.call('GET', KEYS[i])
    if value and tonumber(value) < 1 then
        return ruleset[KEYS[i]][2]
    end
end

-- Decrease limits
for i, key in pairs(KEYS) do
    redis.call('DECR', key)
end
return 0
"""


class RedisBackend(BaseBackend):
    def __init__(self, redis: StrictRedis) -> None:
        self._redis = redis
        self.lua_script: Script = self._redis.register_script(SCRIPT)

    async def set_block_time(self, user: str, block_time: int) -> None:
        await self._redis.set(f"blocking:{user}", 1, block_time)

    async def is_blocking(self, user: str) -> int:
        return int(await self._redis.ttl(f"blocking:{user}"))

    async def retry_after(self, path: str, user: str, rule: Rule) -> int:
        block_time = await self.is_blocking(user)
        if block_time > 0:
            return block_time

        ruleset = rule.ruleset(path, user)
        retry_after = int(
            await self.lua_script(keys=list(ruleset.keys()), args=[json.dumps(ruleset)])
        )

        if retry_after > 0 and rule.block_time:
            await self.set_block_time(user, rule.block_time)
            retry_after = rule.block_time

        return retry_after
