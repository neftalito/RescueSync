from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Aísla cada prueba de persistencia dentro de una transacción reversible."""

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
