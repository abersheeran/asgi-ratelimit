from abc import ABC, abstractmethod

from ..rule import Rule


class BaseBackend(ABC):
    """
    Base class for all backend
    """

    @abstractmethod
    async def retry_after(self, path: str, user: str, rule: Rule) -> int:
        raise NotImplementedError
