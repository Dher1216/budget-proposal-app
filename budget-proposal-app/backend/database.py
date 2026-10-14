"""
Database connection.

Default: local SQLite file (budget.db) -- fine for getting started and for
small deployments. For 30+ offices hitting this over the internet at once,
swap SQLALCHEMY_DATABASE_URL for a real Postgres URL, e.g.:

    postgresql+psycopg2://user:password@host:5432/budget_db

and add `psycopg2-binary` to requirements.txt. No other code changes needed.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./budget.db")

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
