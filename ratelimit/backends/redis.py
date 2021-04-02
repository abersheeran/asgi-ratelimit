from aredis import StrictRedis
from aredis.pipeline import StrictPipeline, WatchError

from ..rule import RULENAMES, Rule
from . import BaseBackend


DECREASE_SCRIPT = """
for i = 1, #KEYS do
    local value = redis.pcall('GET', KEYS[i])
    if value and tonumber(value) < 1 then
        return 0
    end
end
for i, key in pairs(KEYS) do
    redis.pcall('DECR', key)
end
return 1
"""


class RedisBackend(BaseBackend):
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
        self.decrease_function = self._redis.register_script(DECREASE_SCRIPT)

    async def increase_limit(self, path: str, user: str, rule: Rule) -> None:
        """
        Return True means successful increase.
        """
        async with await self._redis.pipeline() as pipe:  # type: StrictPipeline
            try:
                await pipe.watch(*[f"{path}:{user}:{name}" for name in RULENAMES])
                pipe.multi()
                for key, (count, ttl) in rule.ruleset(path, user).items():
                    await pipe.set(key, count, ex=ttl, nx=True)
                await pipe.execute()
            except WatchError:  # pragma: no cover
                pass
            finally:
                await pipe.reset()

    async def decrease_limit(self, path: str, user: str, rule: Rule) -> bool:
        """
        Return True means successful decrease.
        """
        names = [
            f"{path}:{user}:{name}"
            for name in RULENAMES
            if getattr(rule, name) is not None
        ]
        # from tests.backends.test_redis import logger
        # logger.debug(f"{path} {user} : {rule}, {{key: await self._redis.get(key) for key in names}}")
        is_success = await self.decrease_function.execute(keys=names)
        return bool(is_success)

    async def set_block_time(self, user: str, block_time: int) -> None:
        await self._redis.set(f"blocking:{user}", True, block_time)

    async def is_blocking(self, user: str) -> bool:
        return bool(await self._redis.get(f"blocking:{user}"))

    async def allow_request(self, path: str, user: str, rule: Rule) -> bool:
        if await self.is_blocking(user):
            return False

        await self.increase_limit(path, user, rule)
        allow = await self.decrease_limit(path, user, rule)

        if not allow and rule.block_time:
            await self.set_block_time(user, rule.block_time)

        return allow
