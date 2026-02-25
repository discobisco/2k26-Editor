from __future__ import annotations

import uvicorn

from nba2k_editor.mcp_server.app import create_app
from nba2k_editor.mcp_server.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "nba2k_editor.mcp_server.app:create_app",
        host=settings.host,
        port=settings.port,
        factory=True,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
