from __future__ import annotations

import uvicorn

from .api import create_app
from .settings import HubSettings


SETTINGS = HubSettings.from_env()
APP = create_app(SETTINGS)


def run() -> None:
    uvicorn.run(
        "stream_hub_backend.main:APP",
        host="0.0.0.0",
        port=SETTINGS.port,
        access_log=False,
    )


if __name__ == "__main__":
    run()
