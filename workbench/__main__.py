"""Module entrypoint.

Run: python -m workbench
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("WORKBENCH_HOST", "127.0.0.1")
    port = int(os.getenv("WORKBENCH_PORT", "8000"))

    uvicorn.run(
        "workbench.api.app:app",
        host=host,
        port=port,
        reload=bool(os.getenv("WORKBENCH_RELOAD")),
    )


if __name__ == "__main__":
    main()
