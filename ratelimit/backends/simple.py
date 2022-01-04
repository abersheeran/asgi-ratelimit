import asyncio
import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List

from ..rule import Rule
from . import BaseBackend

lock = Lock()


def synchronized(func):
    def wrapper(*args, **kwargs):
        try:
            lock.acquire()
            return func(*args, **kwargs)
        finally:
            lock.release()

    return wrapper


class MemoryBackend(BaseBackend):
    """simple limiter with memory"""

    def __init__(self):
        # user: deadline
        self.blocked_users: Dict[str, int] = {}
        # path: {rule_key: (limit, timestamp)}
        self.blocks: Dict[str, Dict[str, List[int]]] = defaultdict(dict)

    @staticmethod
    def now() -> int:
        return int(time.time())

    def is_blocking(self, user: str) -> int:
        end_ts: int = self.blocked_users.get(user, 0)
        return max(end_ts - self.now(), 0)

    @synchronized
    def remove_user(self, user: str):
        self.blocked_users.pop(user, None)

    @synchronized
    def remove_rule(self, path: str, rule_key: str):
        self.blocks[path].pop(rule_key, None)

    def remove_blocked_user_later(self, user: str):
        loop = asyncio.get_event_loop()
        later = self.blocked_users[user]
        loop.call_at(later, lambda: self.remove_user(user))

    def remove_rule_later(self, path: str, rule_key: str):
        loop = asyncio.get_event_loop()
        _, deadline = self.blocks[path][rule_key]
        loop.call_at(deadline, lambda: self.remove_rule(path, rule_key))

    def set_blocked_user(self, user: str, block_time: int) -> int:
        self.blocked_users[user] = block_time + self.now()
        self.remove_blocked_user_later(user)
        return block_time

    @synchronized
    async def retry_after(self, path: str, user: str, rule: Rule) -> int:
        block_time = self.is_blocking(user)
        if block_time > 0:
            return block_time
        ruleset = rule.ruleset(path, user)

        now = self.now()
        rules = self.blocks.setdefault(path, {})

        retry_after: int = 0

        for rule_, (limit, seconds) in ruleset.items():
            exist_rule = rules.get(rule_)
            if not exist_rule:
                rules[rule_] = [limit - 1, now + seconds]
                self.remove_rule_later(path, rule_)
            else:
                if exist_rule[0] < 1 and exist_rule[1] > now:
                    retry_after = exist_rule[1] - now
                    break
                if exist_rule[0] < 1 and exist_rule[1] < now:
                    rules[rule_] = [limit - 1, now + seconds]
                    self.remove_rule_later(path, rule_)
                elif exist_rule[1] > now:
                    exist_rule[0] -= 1
                else:
                    rules[rule_] = [limit - 1, now + seconds]
                    self.remove_rule_later(path, rule_)

        if retry_after > 0 and rule.block_time:
            retry_after = self.set_blocked_user(user, rule.block_time)

        return retry_after
