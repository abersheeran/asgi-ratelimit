import time

from aredis import StrictRedis
from aredis.pipeline import StrictPipeline, WatchError

from ..rule import Rule, RULENAMES
from . import BaseBackend

DECREASE_SCRIPT = """
for i, key in ipairs(KEYS) do
    local value = tonumber(redis.call('GET', key))
    if not value or value < 1 then
        return false
    end
end
for i, key in ipairs(KEYS) do
    redis.call('DECR', key)
end
return true
"""


class RedisBackend(BaseBackend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = None,
    ) -> None:
        self._redis = StrictRedis(host=host, port=port, db=db, password=password)
        self.decrease_function = self._redis.register_script(DECREASE_SCRIPT)

    async def increase_limit(self, path: str, user: str, rule: Rule) -> bool:
        """
        Return True means successful increase.
        """
        async with await self._redis.pipeline() as pipe:  # type: StrictPipeline
            try:
                timestamp = time.time()
                await pipe.watch(
                    *[f"{path}:{user}:{name}:last_modify" for name in RULENAMES]
                )
                pipe.multi()
                [
                    await pipe.get(f"{path}:{user}:{name}:last_modify")
                    for name in RULENAMES
                ]
                result = [
                    None if _timestamp is None else float(_timestamp)
                    for _timestamp in await pipe.execute()
                ]
                incr_dict = self.calc_incr_value(result, rule)
                if not incr_dict:
                    return False

                pipe.multi()
                for name, data in incr_dict.items():
                    await pipe.set(f"{path}:{user}:{name}", data["value"], data["ttl"])
                    await pipe.set(
                        f"{path}:{user}:{name}:last_modify", timestamp, data["ttl"],
                    )
                await pipe.execute()
                return True
            except WatchError:  # pragma: no cover
                return False

    async def decrease_limit(self, path: str, user: str, rule: Rule) -> bool:
        """
        Return True means successful decrease.
        """
        return await self.decrease_function.execute(
            keys=[
                f"{path}:{user}:{name}"
                for name in RULENAMES
                if getattr(rule, name) is not None
            ]
        )
