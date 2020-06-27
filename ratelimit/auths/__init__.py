from ..types import Scope


class EmptyInformation(Exception):
    def __init__(self, scope: Scope) -> None:
        self.scope = scope
