import ipaddress
import re
from dataclasses import dataclass


def normalize_host(value: str) -> str:
    """Normalize one exact hostname or IP, never a URL, port or wildcard."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("HTTP allowed hosts must be exact hostnames")
    host = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    if any(character in host for character in "/\\@?#%*"):
        raise ValueError("HTTP allowed hosts must be exact hostnames")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    try:
        host = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("HTTP allowed hosts must be valid hostnames") from None
    if not host or len(host) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in host.split(".")
    ):
        raise ValueError("HTTP allowed hosts must be valid hostnames")
    return host


def public_address(value: str) -> bool:
    """Exclude private/special ranges and address-translation bypasses."""
    if not isinstance(value, str) or "%" in value:
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if address == ipaddress.ip_address("168.63.129.16"):
        return False  # Azure platform/metadata-facing virtual address.
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
        if address in ipaddress.ip_network("64:ff9b::/96"):
            return False
        if address in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return True


@dataclass(frozen=True)
class HTTPPolicy:
    allowed_hosts: tuple[str, ...] = ()
    allow_insecure: bool = False
    max_request_bytes: int = 65_536
    max_response_bytes: int = 262_144

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_hosts, (tuple, list)):
            raise ValueError("HTTP allowed hosts must be a list of exact hostnames")
        object.__setattr__(
            self, "allowed_hosts", tuple(dict.fromkeys(normalize_host(host) for host in self.allowed_hosts))
        )
        if type(self.allow_insecure) is not bool:
            raise ValueError("HTTP insecure permission must be boolean")
        for limit in (self.max_request_bytes, self.max_response_bytes):
            if type(limit) is not int or limit <= 0:
                raise ValueError("HTTP body limits must be positive integers")
