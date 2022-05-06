import asyncio
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional

from ..rule import Rule
from . import BaseBackend


@dataclass
class Limit:
    count: int
    timestamp: int

    def decr(self) -> bool:
        self.count -= 1
        return self.count >= 0


class MemoryBackend(BaseBackend):
    """simple limiter with memory"""

    def __init__(self):
        # user: deadline
        self.blocked_users: Dict[str, int] = {}
        # path: {rule_key: (limit, timestamp)}
        self.blocks: Dict[str, Dict[str, Limit]] = defaultdict(dict)

        self.blocks_lock = Lock()
        self.blocked_users_lock = Lock()

    @staticmethod
    def now() -> int:
        loop = asyncio.get_event_loop()
        return int(loop.time())

    @staticmethod
    def call_later(later, callback, *args) -> asyncio.TimerHandle:
        loop = asyncio.get_event_loop()
        return loop.call_later(later, callback, *args)

    def is_blocking(self, user: str) -> int:
        end_ts: int = self.blocked_users.get(user, 0)
        return max(end_ts - self.now(), 0)

    def remove_user(self, user: str) -> Optional[int]:
        with self.blocked_users_lock:
            return self.blocked_users.pop(user, None)

    def remove_rule(self, path: str, rule_key: str) -> Optional[Limit]:
        with self.blocks_lock:
            return self.blocks[path].pop(rule_key, None)

    def remove_blocked_user_later(self, user: str) -> None:
        later = self.blocked_users[user]
        self.call_later(later, self.remove_user, user)

    def remove_rule_later(self, path: str, rule_key: str) -> None:
        rule = self.blocks[path][rule_key]
        self.call_later(rule.timestamp, self.remove_rule, path, rule_key)

    def set_blocked_user(self, user: str, block_time: int) -> int:
        self.blocked_users[user] = block_time + self.now()
        self.remove_blocked_user_later(user)
        return block_time

    def set_rule(
        self,
        rules: Dict[str, Limit],
        path: str,
        rule: str,
        limit: int,
        timestamp: int,
    ) -> Limit:
        obj = Limit(limit, timestamp)
        rules[rule] = obj
        self.remove_rule_later(path, rule)
        return obj

    async def retry_after(self, path: str, user: str, rule: Rule) -> int:
        block_time = self.is_blocking(user)
        if block_time > 0:
            return block_time
        ruleset = rule.ruleset(path, user)

        now = self.now()
        rules = self.blocks.setdefault(path, {})

        retry_after: int = 0

        for rule_, (limit, seconds) in ruleset.items():
            exist_rule = rules.get(rule_) or self.set_rule(
                rules, path, rule_, limit, now + seconds
            )
            if exist_rule.timestamp < now:
                exist_rule = self.set_rule(rules, path, rule_, limit, now + seconds)
            if exist_rule.decr():
                continue
            else:
                retry_after = exist_rule.timestamp - now
                break

        if retry_after > 0 and rule.block_time:
            retry_after = self.set_blocked_user(user, rule.block_time)

        return retry_after
