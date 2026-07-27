import pytest
from sqlalchemy import text

from etl.utils.db import get_engine


@pytest.fixture(scope="session")
def engine():
    return get_engine()


@pytest.fixture(scope="session")
def conn(engine):
    with engine.connect() as connection:
        yield connection


def scalar(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()
