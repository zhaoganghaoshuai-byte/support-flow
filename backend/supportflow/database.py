from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .models import Base


def make_database(url: str):
    sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 15} if sqlite else {},
        pool_pre_ping=True,
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def pragmas(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")

    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)
