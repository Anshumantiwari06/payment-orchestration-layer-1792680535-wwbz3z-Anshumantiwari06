
import os

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME"),
)

if not os.getenv("DB_USER") or not os.getenv("DB_PASSWORD") or not os.getenv("DB_NAME"):
    raise RuntimeError("Database configuration is incomplete")
