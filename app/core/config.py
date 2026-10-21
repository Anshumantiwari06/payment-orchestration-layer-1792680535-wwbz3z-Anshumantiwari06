
import os

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

missing = [
    name
    for name, value in {
        "DB_USER": DB_USER,
        "DB_PASSWORD": DB_PASSWORD,
        "DB_NAME": DB_NAME,
    }.items()
    if not value
]

if missing:
    raise RuntimeError(
        "Missing required database configuration: "
        + ", ".join(missing)
    )

try:
    port = int(DB_PORT)
except ValueError as exc:
    raise RuntimeError("DB_PORT must be a valid integer") from exc

if not 1 <= port <= 65535:
    raise RuntimeError("DB_PORT must be between 1 and 65535")

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=port,
    database=DB_NAME,
)
