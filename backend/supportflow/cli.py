import os

import uvicorn

from .config import Settings


def main():
    Settings.load()
    uvicorn.run(
        "supportflow.app:create_app",
        factory=True,
        host=os.getenv("SUPPORTFLOW_HOST", "127.0.0.1"),
        port=int(os.getenv("SUPPORTFLOW_PORT", "8010")),
        workers=1,
    )


if __name__ == "__main__":
    main()
