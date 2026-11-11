import ipaddress
import socket
from urllib.parse import urlparse


class URLSecurityError(ValueError):
    """Raised when a navigation target is not an approved public HTTPS URL."""


def validate_survey_url(url: str, approved_domains: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise URLSecurityError("Only HTTPS survey URLs are allowed.")
    if parsed.username or parsed.password:
        raise URLSecurityError("Survey URLs must not contain credentials.")
    if parsed.port not in (None, 443):
        raise URLSecurityError("Survey URLs must use HTTPS port 443.")
    host = parsed.hostname.rstrip(".").casefold()
    domains = tuple(domain.rstrip(".").casefold() for domain in approved_domains if domain.strip())
    if not domains or not any(host == domain or host.endswith(f".{domain}") for domain in domains):
        raise URLSecurityError("Survey host is not an approved domain.")
    _reject_private_address(host)
    return parsed.geturl()


def validate_request_url(url: str, approved_domains: tuple[str, ...]) -> str:
    """Validate every browser request; DNS is re-resolved for each request."""
    return validate_survey_url(url, approved_domains)


def _reject_private_address(host: str) -> None:
    try:
        addresses = [host]
        ipaddress.ip_address(host)
    except ValueError:
        try:
            addresses = [item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
        except OSError as exc:
            raise URLSecurityError("Survey host could not be resolved safely.") from exc
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise URLSecurityError("Survey host resolved to an invalid address.") from exc
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise URLSecurityError("Survey host resolves to a blocked network address.")
