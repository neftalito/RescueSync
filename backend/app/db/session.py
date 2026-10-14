from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def get_db_consolidado() -> Generator[Session, None, None]:
    """El GET técnico lee todos sus datos desde el mismo snapshot local."""
    with Session(
        engine.execution_options(isolation_level="REPEATABLE READ"),
        autoflush=False,
        expire_on_commit=False,
    ) as session:
        yield session
