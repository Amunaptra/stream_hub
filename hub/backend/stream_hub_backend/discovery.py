from __future__ import annotations

import logging
import socket

from zeroconf import ServiceInfo, Zeroconf


LOGGER = logging.getLogger("stream-hub.discovery")
SERVICE_TYPE = "_stream-hub._tcp.local."


def local_ipv4_address() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class HubAdvertiser:
    def __init__(self, port: int):
        address = socket.inet_aton(local_ipv4_address())
        self.zeroconf = Zeroconf()
        self.info = ServiceInfo(
            SERVICE_TYPE,
            f"Stream Hub.{SERVICE_TYPE}",
            addresses=[address],
            port=port,
            properties={"api": "v1", "scheme": "http"},
            server=f"{socket.gethostname()}.local.",
        )
        self.registered = False

    def start(self) -> None:
        self.zeroconf.register_service(self.info)
        self.registered = True
        LOGGER.info("advertising Hub at %s:%s", local_ipv4_address(), self.info.port)

    def close(self) -> None:
        if self.registered:
            self.zeroconf.unregister_service(self.info)
        self.zeroconf.close()
