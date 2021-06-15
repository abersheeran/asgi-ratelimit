from abc import ABC, abstractmethod

from ..rule import Rule


class BaseBackend(ABC):
    """
    Base class for all backend
    """

    @abstractmethod
    async def allow_request(self, path: str, user: str, rule: Rule) -> bool:
        raise NotImplementedError
