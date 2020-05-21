import time

from aredis import StrictRedis
from aredis.pipeline import StrictPipeline, WatchError

from ..rule import Rule, RULENAMES
from . import BaseBackend


class RedisBackend(BaseBackend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = None,
    ) -> None:
        self._redis = StrictRedis(host=host, port=port, db=db, password=password)

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
            except WatchError:
                return False

    async def decrease_limit(self, path: str, user: str, rule: Rule) -> bool:
        """
        Return True means successful decrease.
        """
        async with await self._redis.pipeline() as pipe:  # type: StrictPipeline
            for _ in range(3):
                try:
                    await pipe.watch(*[f"{path}:{user}:{name}" for name in RULENAMES])

                    pipe.multi()
                    [await pipe.get(f"{path}:{user}:{name}") for name in RULENAMES]
                    result = await pipe.execute()

                    for i in filter(lambda x: x is not None, result):
                        if int(i) < 1:
                            return False

                    pipe.multi()
                    [await pipe.decr(f"{path}:{user}:{name}") for name in RULENAMES]
                    await pipe.execute()

                    return True
                except WatchError:
                    continue
            return False
