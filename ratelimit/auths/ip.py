from typing import Tuple
from ipaddress import ip_address

from ..types import Scope


async def client_ip(scope: Scope) -> Tuple[str, str]:
    """
    parse ip
    """
    real_ip = ""
    if scope["client"]:
        ip, port = tuple(scope["client"])
        if ip_address(ip).is_global:
            real_ip = ip

    for name, value in scope["headers"]:  # type: bytes, bytes
        if name == b"x-forwarded-for":
            ip = value.decode("utf8").split(",")[0].strip()
        elif name == b"x-real-ip":
            ip = value.decode("utf8")
        else:  # no ip to set
            continue
        if not real_ip and ip_address(ip).is_global:
            real_ip = ip

    if not real_ip:
        return "no-ip-client", "dont-found-ip"
    return real_ip, "default"
