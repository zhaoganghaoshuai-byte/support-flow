import argparse
import json
import os

import uvicorn

from .config import Settings
from .database import make_engine
from .migration import database_revision, migrate_database


def main():
    parser = argparse.ArgumentParser(description="SupportFlow single-process application")
    parser.add_argument(
        "command", nargs="?", choices=["serve", "migrate", "db-status"], default="serve"
    )
    arguments = parser.parse_args()
    settings = Settings.load()
    if arguments.command != "serve":
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = make_engine(settings.database_url)
        try:
            if arguments.command == "migrate":
                migrate_database(engine)
            print(json.dumps(database_revision(engine)))
        finally:
            engine.dispose()
        return
    uvicorn.run(
        "supportflow.app:create_app",
        factory=True,
        host=os.getenv("SUPPORTFLOW_HOST", "127.0.0.1"),
        port=int(os.getenv("SUPPORTFLOW_PORT", "8010")),
        workers=1,
    )


if __name__ == "__main__":
    main()
