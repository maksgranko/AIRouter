from typing import Dict, Optional, Any

from httpx_socks import AsyncProxyTransport


def get_httpx_proxies(proxy_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not proxy_config:
        return None

    proxy_type = proxy_config.get("type")
    proxy_url = proxy_config.get("url")
    if not proxy_url:
        return None

    if proxy_type in ["http", "https", "socks4", "socks5"]:
        return {
            "http://": proxy_url,
            "https://": proxy_url,
        }
    return None


def build_async_client_args(httpx_proxies: Optional[Dict[str, str]], timeout: float = 60.0) -> Dict[str, Any]:
    client_args: Dict[str, Any] = {"timeout": timeout}
    if not httpx_proxies:
        return client_args

    proxy_url = httpx_proxies.get("http://")
    if proxy_url and proxy_url.startswith(("socks5://", "socks4://")):
        client_args["transport"] = AsyncProxyTransport.from_url(proxy_url)
    else:
        client_args["proxies"] = httpx_proxies
    return client_args
