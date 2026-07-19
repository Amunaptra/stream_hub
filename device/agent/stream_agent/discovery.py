from __future__ import annotations

import threading

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


SERVICE_TYPE = "_stream-hub._tcp.local."


class _HubListener(ServiceListener):
    def __init__(self, zeroconf: Zeroconf):
        self.zeroconf = zeroconf
        self.event = threading.Event()
        self.url: str | None = None

    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        info = zeroconf.get_service_info(service_type, name, timeout=1500)
        if not info:
            return
        addresses = info.parsed_scoped_addresses()
        if not addresses:
            return
        scheme = (info.properties.get(b"scheme", b"http") or b"http").decode()
        self.url = f"{scheme}://{addresses[0]}:{info.port}"
        self.event.set()

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        self.add_service(zeroconf, service_type, name)

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None


def discover_hub(timeout_seconds: float = 3.0) -> str | None:
    zeroconf = Zeroconf()
    listener = _HubListener(zeroconf)
    browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener)
    try:
        listener.event.wait(timeout_seconds)
        return listener.url
    finally:
        browser.cancel()
        zeroconf.close()
