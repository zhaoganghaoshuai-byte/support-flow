"""Bootstrap a real account without placing a password in shell history."""

import argparse
import getpass
import os

from sqlalchemy import select
from supportflow.config import Settings
from supportflow.database import make_database
from supportflow.models import User
from supportflow.security import hash_password

parser = argparse.ArgumentParser()
parser.add_argument("--email", required=True)
parser.add_argument("--name", required=True)
parser.add_argument("--role", choices=["requester", "engineer", "admin"], default="requester")
args = parser.parse_args()
password = os.getenv("SUPPORTFLOW_BOOTSTRAP_PASSWORD") or getpass.getpass(
    "Password (at least 12 characters): "
)
if len(password) < 12:
    raise SystemExit("Password must have at least 12 characters")
settings = Settings.load()
settings.data_dir.mkdir(parents=True, exist_ok=True)
engine, sessions = make_database(settings.database_url)
with sessions() as db:
    if db.scalar(select(User).where(User.email == args.email.casefold())):
        raise SystemExit("Account already exists")
    db.add(
        User(
            email=args.email.casefold(),
            name=args.name,
            role=args.role,
            password_hash=hash_password(password),
        )
    )
    db.commit()
engine.dispose()
print("Account created.")
