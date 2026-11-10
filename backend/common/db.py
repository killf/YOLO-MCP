import sqlite3
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import Session, SessionTransaction
from sqlalchemy.orm import sessionmaker
from backend.common.config import settings

database_url = settings.DATABASE_URL
parsed_url = make_url(database_url)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(connection, _record) -> None:
    """每个 SQLite 连接启用外键校验；其他数据库沿用自身的约束实现。"""
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


if parsed_url.get_backend_name() == "sqlite":
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
else:
    engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=3600)

SessionLocal = sessionmaker(autoflush=False, bind=engine)

Base = declarative_base()


def begin_transaction(session: Session) -> SessionTransaction:
    """回滚查询自动开启的事务，再返回写事务；调用前不得积累未提交修改。"""
    if session.in_transaction():
        session.rollback()
    return session.begin()


def get_db() -> Generator[Session, None, None]:
    """为一次请求提供会话，结束时关闭连接并回滚未提交的事务。"""
    with SessionLocal() as session:
        yield session
