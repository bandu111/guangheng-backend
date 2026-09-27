from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# 项目根目录：
# E:\PythonProject\guangheng_server
BASE_DIR = Path(__file__).resolve().parents[2]


# 数据库存储目录：
# E:\PythonProject\guangheng_server\storage
DATABASE_DIR = BASE_DIR / "storage"


# 如果 storage 不存在，则自动创建
DATABASE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# SQLite 数据库文件：
# E:\PythonProject\guangheng_server\storage\guangheng.db
DATABASE_PATH = DATABASE_DIR / "guangheng.db"


# SQLAlchemy 数据库连接 URL
DATABASE_URL = (
    f"sqlite:///{DATABASE_PATH.as_posix()}"
)


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()