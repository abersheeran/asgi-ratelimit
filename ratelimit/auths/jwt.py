from typing import Awaitable, Callable, List, Optional, Tuple, Union

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from ..types import Scope
from . import EmptyInformation


def create_jwt_auth(
    key: Union[bytes, str, RSAPublicKey, RSAPrivateKey],
    algorithms: Union[List[str], str],
) -> Callable[[Scope], Awaitable[Tuple[str, str]]]:
    """
    create jwt authentication function

    * key: for algorithm secret key
    * algorithms: Possible algorithms in https://pyjwt.readthedocs.io/en/latest/algorithms.html#digital-signature-algorithms
    """

    async def jwt_auth(scope: Scope) -> Tuple[str, str]:
        """
        About jwt header, read this link:
        https://stackoverflow.com/questions/33265812/best-http-authorization-header-type-for-jwt
        """
        for name, value in scope["headers"]:  # type: bytes, bytes
            if name == b"authorization":
                authorization: Optional[str] = value.decode("utf8")
                break
        else:
            authorization = None

        if not authorization:
            raise EmptyInformation(scope)

        token_type, json_web_token = authorization.split(" ")

        assert (
            token_type == "Bearer"
        ), "Authorization header must be `Bearer` type. Like: `Bearer LONG_JWT`"

        data = jwt.decode(json_web_token, key, algorithms=algorithms)

        try:
            return data["user"], data.get("group", "default")
        except KeyError:
            raise EmptyInformation(scope)

    return jwt_auth
