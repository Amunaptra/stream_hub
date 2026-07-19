from __future__ import annotations

import uvicorn

from .api import create_app
from .settings import Settings


APP = create_app()


def run() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "stream_agent.main:APP",
        host="0.0.0.0",
        port=settings.agent_port,
        access_log=False,
    )


if __name__ == "__main__":
    run()
