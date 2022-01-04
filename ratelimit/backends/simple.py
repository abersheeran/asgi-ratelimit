import asyncio
import time
from asyncio import TimerHandle
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Optional

from . import BaseBackend
from ..rule import Rule

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

    @staticmethod
    def call_at(later, callback, *args) -> TimerHandle:
        loop = asyncio.get_event_loop()
        return loop.call_at(later, callback, *args)

    def is_blocking(self, user: str) -> int:
        end_ts: int = self.blocked_users.get(user, 0)
        return max(end_ts - self.now(), 0)

    @synchronized
    def remove_user(self, user: str) -> Optional[int]:
        return self.blocked_users.pop(user, None)

    @synchronized
    def remove_rule(self, path: str, rule_key: str) -> Optional[List[int]]:
        return self.blocks[path].pop(rule_key, None)

    def remove_blocked_user_later(self, user: str):
        later = self.blocked_users[user]
        self.call_at(later, self.remove_user, user)

    def remove_rule_later(self, path: str, rule_key: str):
        _, deadline = self.blocks[path][rule_key]
        return self.call_at(deadline, self.remove_rule, path, rule_key)

    def set_blocked_user(self, user: str, block_time: int) -> int:
        self.blocked_users[user] = block_time + self.now()
        self.remove_blocked_user_later(user)
        return block_time

    def set_rule(self, rules: Dict, path: str, rule: str, limit: int, timestamp: int):
        rules[rule] = [limit - 1, timestamp]
        self.remove_rule_later(path, rule)

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
                self.set_rule(rules, path, rule_, limit, now + seconds)
            else:
                if exist_rule[0] < 1 and exist_rule[1] > now:
                    retry_after = exist_rule[1] - now
                    break
                if exist_rule[0] < 1 and exist_rule[1] < now:
                    self.set_rule(rules, path, rule_, limit, now + seconds)
                elif exist_rule[1] > now:
                    exist_rule[0] -= 1
                else:
                    self.set_rule(rules, path, rule_, limit, now + seconds)

        if retry_after > 0 and rule.block_time:
            retry_after = self.set_blocked_user(user, rule.block_time)

        return retry_after
