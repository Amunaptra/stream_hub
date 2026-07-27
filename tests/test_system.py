from __future__ import annotations

import json
import socket
import subprocess

from stream_agent.system import SystemController


def test_ip_addresses_are_read_from_global_network_interfaces(monkeypatch) -> None:
    payload = [
        {
            "ifname": "eth0",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "192.168.102.221",
                    "scope": "global",
                }
            ],
        },
        {
            "ifname": "tailscale0",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "100.100.100.100",
                    "scope": "global",
                }
            ],
        },
    ]
    monkeypatch.setattr(
        SystemController,
        "_run",
        staticmethod(
            lambda command, timeout=10: subprocess.CompletedProcess(
                command, 0, json.dumps(payload), ""
            )
        ),
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("hostname fallback must not run")
        ),
    )

    assert SystemController.ip_addresses() == [
        "100.100.100.100",
        "192.168.102.221",
    ]


def test_ip_addresses_fall_back_to_hostname_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        SystemController,
        "_run",
        staticmethod(
            lambda command, timeout=10: subprocess.CompletedProcess(
                command, 1, "", "ip failed"
            )
        ),
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.1.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.102.228", 0)),
        ],
    )

    assert SystemController.ip_addresses() == ["192.168.102.228"]
